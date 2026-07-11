"""
Participant router — public-facing endpoints for event participants
POST /api/participant/discover  → resolve access code to event
GET  /e/{code}/photos           → list photos
POST /e/{code}/photos           → upload photo
GET  /e/{code}/photos/{id}/url  → get presigned download URL
DELETE /e/{code}/photos/{id}    → delete photo
"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from db import (
    validate_participant_code,
    get_event,
    list_photos as db_list_photos,
    get_photo,
    create_photo_record,
    delete_photo_record,
    log_activity,
    get_access_code,
)
from storage import generate_presigned_post, delete_photo, get_presigned_url
from models import PhotoOut, UploadUrlRequest, UploadConfirmRequest

router = APIRouter(tags=["participant"])

PERMISSIONS = {
    "VIEW_ONLY": {"view"},
    "VIEW_UPLOAD": {"view", "upload"},
    "VIEW_UPLOAD_DELETE": {"view", "upload", "delete"},
}

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic",
}

MAX_FILE_SIZE_MB = 20


async def _resolve_participant(request: Request) -> dict:
    """
    Resolve participant from X-Participant-Code header or cookie.
    Returns the access code record with event_code.
    """
    code = (
        request.headers.get("X-Participant-Code")
        or request.cookies.get("participant_code")
    )
    if not code:
        raise HTTPException(401, "Access code required. Include X-Participant-Code header.")

    item = await validate_participant_code(code.upper())
    if not item:
        raise HTTPException(403, "Invalid or revoked access code")

    return item


def _require_permission(action: str):
    async def dep(request: Request) -> dict:
        ac = await _resolve_participant(request)
        allowed = PERMISSIONS.get(ac["permission"], set())
        if action not in allowed:
            raise HTTPException(403, f"Your access code does not permit '{action}'")
        return ac
    return dep


@router.post("/api/participant/discover")
async def discover_event(request: Request):
    """Given an X-Participant-Code header, return the event_code + permission."""
    ac = await _resolve_participant(request)
    event = await get_event(ac["event_code"])
    if not event:
        raise HTTPException(404, "Event not found")

    return {
        "event_code": ac["event_code"],
        "permission": ac["permission"],
        "label": ac.get("label", ""),
        "event_name": event.get("event_name", ""),
    }


@router.get("/e/{code}/photos", response_model=list[PhotoOut])
async def list_photos_endpoint(code: str, request: Request):
    ac = await _resolve_participant(request)
    allowed = PERMISSIONS.get(ac["permission"], set())
    if "view" not in allowed:
        raise HTTPException(403, "Your access code does not permit viewing")

    event_code = ac["event_code"]
    ip = request.client.host if request.client else None
    await log_activity(event_code, ac["code"], "VIEW", ip_address=ip)

    photos = await db_list_photos(event_code)

    # Look up uploader labels
    result = []
    for p in photos:
        uploader_code = p.get("access_code", "")
        uploader_ac = await get_access_code(event_code, uploader_code) if uploader_code else None

        result.append(PhotoOut(
            id=p["id"],
            url=get_presigned_url(p["s3_key"]),
            download_url=get_presigned_url(p["s3_key"], download_filename=p.get("original_name")),
            original_name=p.get("original_name"),
            content_type=p.get("content_type", "image/jpeg"),
            uploaded_at=p["uploaded_at"],
            uploaded_by_label=uploader_ac.get("label") if uploader_ac else None,
        ))

    return result


@router.post("/e/{code}/photos/upload-url")
async def get_upload_url_endpoint(
    code: str,
    request: Request,
    body: UploadUrlRequest,
):
    ac = await _resolve_participant(request)
    allowed = PERMISSIONS.get(ac["permission"], set())
    if "upload" not in allowed:
        raise HTTPException(403, "Your access code does not permit uploading")

    if body.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"Unsupported file type: {body.content_type}")

    event_code = ac["event_code"]
    photo_id, s3_key, presigned_data = generate_presigned_post(
        event_code=event_code,
        filename=body.filename or "photo.jpg",
        content_type=body.content_type,
        max_size_mb=MAX_FILE_SIZE_MB,
    )

    return {
        "photo_id": photo_id,
        "s3_key": s3_key,
        "url": presigned_data["url"],
        "fields": presigned_data["fields"],
    }


@router.post("/e/{code}/photos/confirm", status_code=201)
async def confirm_upload_endpoint(
    code: str,
    request: Request,
    body: UploadConfirmRequest,
):
    ac = await _resolve_participant(request)
    allowed = PERMISSIONS.get(ac["permission"], set())
    if "upload" not in allowed:
        raise HTTPException(403, "Your access code does not permit uploading")

    event_code = ac["event_code"]

    await create_photo_record(
        event_code=event_code,
        photo_id=body.photo_id,
        s3_key=body.s3_key,
        original_name=body.original_name or "photo.jpg",
        content_type=body.content_type,
        access_code=ac["code"],
    )

    ip = request.client.host if request.client else None
    await log_activity(event_code, ac["code"], "UPLOAD", photo_id=body.photo_id, ip_address=ip)

    return {
        "id": body.photo_id,
        "url": get_presigned_url(body.s3_key),
        "download_url": get_presigned_url(body.s3_key, download_filename=body.original_name),
        "original_name": body.original_name,
        "content_type": body.content_type,
        "uploaded_at": None, # Will be set by client or DB read
    }


@router.delete("/e/{code}/photos/{photo_id}", status_code=204)
async def delete_photo_endpoint(code: str, photo_id: str, request: Request):
    ac = await _resolve_participant(request)
    allowed = PERMISSIONS.get(ac["permission"], set())
    if "delete" not in allowed:
        raise HTTPException(403, "Your access code does not permit deleting")

    event_code = ac["event_code"]
    photo = await get_photo(event_code, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")

    await delete_photo(photo["s3_key"])
    await delete_photo_record(event_code, photo_id)

    ip = request.client.host if request.client else None
    await log_activity(event_code, ac["code"], "DELETE", photo_id=photo_id, ip_address=ip)
