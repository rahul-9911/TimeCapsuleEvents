"""
Access Codes router — organiser manages participant codes
POST   /api/events/{code}/codes           → create code
GET    /api/events/{code}/codes           → list codes
DELETE /api/events/{code}/codes/{code_id} → revoke code
GET    /api/events/{code}/activity        → activity summary
"""
import os
import string
import secrets

from fastapi import APIRouter, Depends, HTTPException

from db import (
    get_event,
    create_access_code,
    list_access_codes,
    revoke_access_code,
    get_activity_summary,
)
from middleware import get_current_organiser
from models import CodeCreate, CodeOut, ActivitySummary

router = APIRouter(tags=["codes"])

CODE_CHARS = string.ascii_uppercase + string.digits
BASE_URL = os.getenv("BASE_URL", "http://localhost")


def _new_access_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(8))


@router.post("/{event_code}/codes", response_model=CodeOut, status_code=201)
async def create_code_endpoint(
    event_code: str,
    body: CodeCreate,
    organiser: dict = Depends(get_current_organiser),
):
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    if body.permission not in ("VIEW_ONLY", "VIEW_UPLOAD", "VIEW_UPLOAD_DELETE"):
        raise HTTPException(400, "permission must be VIEW_ONLY, VIEW_UPLOAD, or VIEW_UPLOAD_DELETE")

    access_code_value = _new_access_code()
    item = await create_access_code(code, access_code_value, body.label, body.permission)

    return CodeOut(
        id=item["id"],
        code=item["code"],
        label=item.get("label"),
        permission=item["permission"],
        share_url=f"{BASE_URL}/join.html?code={item['code']}",
        created_at=item["created_at"],
        revoked=item.get("revoked", False),
    )


@router.get("/{event_code}/codes", response_model=list[CodeOut])
async def list_codes_endpoint(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    items = await list_access_codes(code)
    activity = await get_activity_summary(code)

    # Merge activity stats into code items
    stats_map = {a["code"]: a for a in activity}

    return [
        CodeOut(
            id=item["id"],
            code=item["code"],
            label=item.get("label"),
            permission=item["permission"],
            share_url=f"{BASE_URL}/join.html?code={item['code']}",
            created_at=item["created_at"],
            revoked=item.get("revoked", False),
            views=stats_map.get(item["code"], {}).get("views", 0),
            uploads=stats_map.get(item["code"], {}).get("uploads", 0),
            deletes=stats_map.get(item["code"], {}).get("deletes", 0),
            last_seen=stats_map.get(item["code"], {}).get("last_seen"),
        )
        for item in items
    ]


@router.delete("/{event_code}/codes/{code_id}", status_code=204)
async def revoke_code_endpoint(
    event_code: str,
    code_id: str,
    organiser: dict = Depends(get_current_organiser),
):
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    await revoke_access_code(code, code_id)


@router.get("/{event_code}/activity", response_model=list[ActivitySummary])
async def get_activity_endpoint(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    summary = await get_activity_summary(code)
    return [ActivitySummary(**s) for s in summary]
