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
)
from storage import delete_event_photos
from middleware import get_current_organiser
from models import EventCreate, EventOut

router = APIRouter(tags=["events"])

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
    )

    return EventOut(
        event_code=event["event_code"],
        event_name=event["event_name"],
        description=event.get("description"),
        event_date=event.get("event_date"),
        status=event["status"],
        created_at=event["created_at"],
        expires_at=event.get("expires_at"),
    )


@router.get("", response_model=list[EventOut])
async def list_events_endpoint(organiser: dict = Depends(get_current_organiser)):
    events = await list_organiser_events(organiser["email"])
    result = []
    for e in events:
        photo_count = await count_photos(e["event_code"])
        codes = await list_access_codes(e["event_code"])
        result.append(EventOut(
            event_code=e["event_code"],
            event_name=e["event_name"],
            description=e.get("description"),
            event_date=e.get("event_date"),
            status=e["status"],
            created_at=e["created_at"],
            expires_at=e.get("expires_at"),
            photo_count=photo_count,
            code_count=len(codes),
        ))
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

    return EventOut(
        event_code=event["event_code"],
        event_name=event["event_name"],
        description=event.get("description"),
        event_date=event.get("event_date"),
        status=event["status"],
        created_at=event["created_at"],
        expires_at=event.get("expires_at"),
        photo_count=photo_count,
        code_count=len(codes),
    )


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
