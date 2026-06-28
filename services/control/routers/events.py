"""
Control Plane — Events router (organiser-only)
POST   /api/events              → create event + spawn container
GET    /api/events              → list organiser's events
GET    /api/events/{event_id}   → event detail
DELETE /api/events/{event_id}   → stop container + delete records
"""
import string
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import get_pool
from middleware import get_current_organiser
from models import EventCreate, EventOut
from spawner import spawn_event, stop_event

router = APIRouter(tags=["events"])

CODE_CHARS = string.ascii_uppercase + string.digits
CODE_LENGTH = 6


def _generate_event_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))


async def _unique_code(conn) -> str:
    for _ in range(10):
        code = _generate_event_code()
        existing = await conn.fetchval("SELECT 1 FROM event_registry WHERE event_code = $1", code)
        if not existing:
            return code
    raise RuntimeError("Failed to generate unique event code after 10 attempts")


@router.post("", response_model=EventOut, status_code=201)
async def create_event(
    body: EventCreate,
    organiser: dict = Depends(get_current_organiser),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check for duplicate event name
        existing = await conn.fetchval(
            "SELECT 1 FROM event_registry WHERE event_name = $1 AND organiser_id = $2",
            body.event_name, organiser["organiser_id"]
        )
        if existing:
            raise HTTPException(400, "You already have an event with this name.")

        code = await _unique_code(conn)

        event = await conn.fetchrow(
            """
            INSERT INTO event_registry
                (organiser_id, event_code, event_name, description, event_date, status)
            VALUES ($1, $2, $3, $4, $5, 'STARTING')
            RETURNING id, event_code, event_name, description, event_date, status, created_at
            """,
            organiser["organiser_id"],
            code,
            body.event_name,
            body.description,
            body.event_date,
        )

    # Spawn the event container asynchronously (don't block the HTTP response)
    import asyncio
    asyncio.create_task(_spawn_and_update(str(event["id"]), code))

    return EventOut(
        id=str(event["id"]),
        event_code=event["event_code"],
        event_name=event["event_name"],
        description=event["description"],
        event_date=event["event_date"],
        status=event["status"],
        created_at=event["created_at"],
    )


async def _spawn_and_update(event_id: str, event_code: str):
    """Background task: spawn container and update internal_url + status."""
    pool = await get_pool()
    try:
        internal_url = await spawn_event(event_code)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE event_registry SET status='RUNNING', internal_url=$1 WHERE id=$2",
                internal_url,
                event_id,
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to spawn event %s: %s", event_code, e)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE event_registry SET status='ERROR' WHERE id=$1",
                event_id,
            )


@router.get("", response_model=list[EventOut])
async def list_events(organiser: dict = Depends(get_current_organiser)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, event_code, event_name, description, event_date, status, created_at
            FROM event_registry
            WHERE organiser_id = $1
            ORDER BY created_at DESC
            """,
            organiser["organiser_id"],
        )
    return [
        EventOut(
            id=str(r["id"]),
            event_code=r["event_code"],
            event_name=r["event_name"],
            description=r["description"],
            event_date=r["event_date"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: str, organiser: dict = Depends(get_current_organiser)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, event_code, event_name, description, event_date, status, created_at
            FROM event_registry
            WHERE id = $1 AND organiser_id = $2
            """,
            event_id,
            organiser["organiser_id"],
        )
    if not row:
        raise HTTPException(404, "Event not found")
    return EventOut(
        id=str(row["id"]),
        event_code=row["event_code"],
        event_name=row["event_name"],
        description=row["description"],
        event_date=row["event_date"],
        status=row["status"],
        created_at=row["created_at"],
    )


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: str, organiser: dict = Depends(get_current_organiser)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT event_code, task_arn FROM event_registry WHERE id=$1 AND organiser_id=$2",
            event_id,
            organiser["organiser_id"],
        )
        if not row:
            raise HTTPException(404, "Event not found")

        await conn.execute("DELETE FROM event_registry WHERE id=$1", event_id)

    # Stop the container and cleanup data in the background
    import asyncio
    from spawner import cleanup_event_data
    
    async def _stop_and_cleanup(code: str, task: str | None):
        await stop_event(code, task)
        await cleanup_event_data(code)
        
    asyncio.create_task(_stop_and_cleanup(row["event_code"], row["task_arn"]))
