"""
Events router — organiser event CRUD
POST   /api/events              → create event
GET    /api/events              → list organiser's events
GET    /api/events/{code}       → event detail
DELETE /api/events/{code}       → delete event + cleanup S3
"""
import string
import secrets

from fastapi import APIRouter, Depends, HTTPException

from db import (
    create_event,
    list_organiser_events,
    get_event,
    delete_event_records,
    event_code_exists,
    event_name_exists_for_organiser,
    count_photos,
    list_access_codes,
    get_active_ai_job_for_event,
)
from storage import delete_event_photos
from middleware import get_current_organiser
from models import EventCreate, EventOut

router = APIRouter()

def _fmt_ai_progress(job: dict | None) -> dict | None:
    if not job:
        return None
    return {
        "processed": int(job.get("processed_photos", 0)),
        "total": int(job.get("total_photos", 0)),
    }


def _event_out(e: dict, photo_count: int = 0, code_count: int = 0, job: dict | None = None) -> EventOut:
    """Build an EventOut from a raw DynamoDB event item + optional job."""
    return EventOut(
        event_code=e["event_code"],
        event_name=e["event_name"],
        description=e.get("description"),
        event_date=e.get("event_date"),
        retention_days=e.get("retention_days", 2),
        status=e["status"],
        created_at=e["created_at"],
        expires_at=e.get("expires_at"),
        photo_count=photo_count,
        code_count=code_count,
        ai_editing_enabled=e.get("ai_editing_enabled", False),
        ai_workflow_id=e.get("ai_workflow_id") or None,
        ai_job_id=e.get("ai_job_id") or None,
        ai_job_status=job["status"] if job else None,
        ai_job_progress=_fmt_ai_progress(job),
        ai_output_event_code=job.get("output_event_code") or None if job else None,
    )


CODE_CHARS = string.ascii_uppercase + string.digits
CODE_LENGTH = 6


def _generate_event_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))


async def _unique_code() -> str:
    for _ in range(10):
        code = _generate_event_code()
        if not await event_code_exists(code):
            return code
    raise RuntimeError("Failed to generate unique event code after 10 attempts")


@router.post("", response_model=EventOut, status_code=201)
async def create_event_endpoint(
    body: EventCreate,
    organiser: dict = Depends(get_current_organiser),
):
    email = organiser["email"]

    # Check for duplicate event name
    if await event_name_exists_for_organiser(email, body.event_name):
        raise HTTPException(400, "You already have an event with this name.")

    code = await _unique_code()
    event_date_str = body.event_date.isoformat() if body.event_date else None

    event = await create_event(
        email=email,
        event_code=code,
        event_name=body.event_name,
        description=body.description,
        event_date=event_date_str,
        retention_days=body.retention_days or 2,
    )

    return _event_out(event)


@router.get("", response_model=list[EventOut])
async def list_events_endpoint(organiser: dict = Depends(get_current_organiser)):
    events = await list_organiser_events(organiser["email"])
    result = []
    for e in events:
        photo_count = await count_photos(e["event_code"])
        codes = await list_access_codes(e["event_code"])
        job = await get_active_ai_job_for_event(e["event_code"]) if e.get("ai_editing_enabled") else None
        result.append(_event_out(e, photo_count=photo_count, code_count=len(codes), job=job))
    return result


@router.get("/{event_code}", response_model=EventOut)
async def get_event_endpoint(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    event = await get_event(event_code.upper())
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    photo_count = await count_photos(event_code.upper())
    codes = await list_access_codes(event_code.upper())
    job = await get_active_ai_job_for_event(event_code.upper()) if event.get("ai_editing_enabled") else None

    return _event_out(event, photo_count=photo_count, code_count=len(codes), job=job)


@router.delete("/{event_code}", status_code=204)
async def delete_event_endpoint(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    # Delete S3 photos
    await delete_event_photos(code)

    # Delete all DynamoDB records for this event
    await delete_event_records(code)
