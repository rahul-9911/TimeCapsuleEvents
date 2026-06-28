"""
Event Worker — All endpoints (participant-facing + internal organiser proxy)
"""
import os
import uuid
import string
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from db import get_db
from models import CodeCreateInternal, CodeOutInternal, PhotoOut, ActivitySummaryOut
from storage import save_photo, delete_photo, get_presigned_url

router = APIRouter()

EVENT_CODE = os.getenv("EVENT_CODE", "UNKNOWN")

PERMISSIONS = {
    "VIEW_ONLY":          {"view"},
    "VIEW_UPLOAD":        {"view", "upload"},
    "VIEW_UPLOAD_DELETE": {"view", "upload", "delete"},
}

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic",
}

MAX_FILE_SIZE_MB = 20
CODE_CHARS = string.ascii_uppercase + string.digits


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _new_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(8))


async def _resolve_participant(request: Request) -> dict:
    """
    Resolve participant from X-Participant-Code header or cookie.
    Returns access_code row or raises 401/403.
    """
    code = (
        request.headers.get("X-Participant-Code")
        or request.cookies.get("participant_code")
    )
    if not code:
        raise HTTPException(401, "Access code required. Include X-Participant-Code header.")

    db = await get_db()
    async with db.execute(
        "SELECT id, code, label, permission, revoked FROM access_codes WHERE code = ?",
        (code.upper(),),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(403, "Invalid access code")
    if row["revoked"]:
        raise HTTPException(403, "This access code has been revoked")
    return dict(row)


def _require_permission(action: str):
    async def dep(request: Request) -> dict:
        ac = await _resolve_participant(request)
        allowed = PERMISSIONS.get(ac["permission"], set())
        if action not in allowed:
            raise HTTPException(403, f"Your access code does not permit '{action}'")
        return ac
    return dep


async def _log(db, access_code_id: str, action: str, photo_id: Optional[str], ip: Optional[str]):
    await db.execute(
        "INSERT INTO activity_log (id, access_code_id, action, photo_id, ip_address) VALUES (?,?,?,?,?)",
        (_new_id(), access_code_id, action, photo_id, ip),
    )
    await db.commit()


# ── Health ─────────────────────────────────────────────────────────────────────
@router.get("/health")
async def health():
    return {"status": "ok", "event_code": EVENT_CODE}


# ── Participant: Event info ────────────────────────────────────────────────────
@router.get("/e/{code}")
async def get_event_info(code: str, request: Request):
    """Public: returns event identity + permission level for this code."""
    ac = await _resolve_participant(request)

    # Set participant cookie on response so subsequent requests carry the code
    resp = JSONResponse({
        "event_code": EVENT_CODE,
        "permission": ac["permission"],
        "label": ac["label"],
    })
    resp.set_cookie(
        "participant_code",
        value=ac["code"],
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return resp


# ── Participant: List photos ───────────────────────────────────────────────────
@router.get("/e/{code}/photos", response_model=list[PhotoOut])
async def list_photos(
    code: str,
    request: Request,
    ac: dict = Depends(_require_permission("view")),
):
    db = await get_db()

    ip = request.client.host if request.client else None
    await _log(db, ac["id"], "VIEW", None, ip)

    async with db.execute(
        """
        SELECT p.id, p.s3_key, p.original_name, p.content_type, p.uploaded_at,
               ac2.label AS uploaded_by_label
        FROM photos p
        JOIN access_codes ac2 ON ac2.id = p.access_code_id
        ORDER BY p.uploaded_at DESC
        """,
    ) as cur:
        rows = await cur.fetchall()

    return [
        PhotoOut(
            id=row["id"],
            url=get_presigned_url(row["s3_key"]),
            original_name=row["original_name"],
            content_type=row["content_type"],
            uploaded_at=row["uploaded_at"],
            uploaded_by_label=row["uploaded_by_label"],
        )
        for row in rows
    ]


# ── Participant: Upload photo ─────────────────────────────────────────────────
@router.post("/e/{code}/photos", status_code=201)
async def upload_photo(
    code: str,
    request: Request,
    file: UploadFile = File(...),
    ac: dict = Depends(_require_permission("upload")),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"Unsupported file type: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large. Max {MAX_FILE_SIZE_MB}MB.")

    photo_id, s3_key = await save_photo(data, file.filename or "photo.jpg", file.content_type)

    db = await get_db()
    await db.execute(
        "INSERT INTO photos (id, access_code_id, s3_key, original_name, content_type) VALUES (?,?,?,?,?)",
        (photo_id, ac["id"], s3_key, file.filename, file.content_type),
    )
    await db.commit()

    ip = request.client.host if request.client else None
    await _log(db, ac["id"], "UPLOAD", photo_id, ip)

    return {"id": photo_id, "url": get_presigned_url(s3_key)}


# ── Participant: Delete photo ─────────────────────────────────────────────────
@router.delete("/e/{code}/photos/{photo_id}", status_code=204)
async def delete_photo_endpoint(
    code: str,
    photo_id: str,
    request: Request,
    ac: dict = Depends(_require_permission("delete")),
):
    db = await get_db()
    async with db.execute("SELECT s3_key FROM photos WHERE id = ?", (photo_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")

    await delete_photo(row["s3_key"])
    await db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    await db.commit()

    ip = request.client.host if request.client else None
    await _log(db, ac["id"], "DELETE", photo_id, ip)


# ── Internal: Code management (called by Control Plane proxy) ─────────────────

@router.post("/internal/codes", response_model=CodeOutInternal, status_code=201)
async def create_code(body: CodeCreateInternal):
    db = await get_db()
    code_id = _new_id()
    code_val = _new_code()

    # Ensure uniqueness
    for _ in range(10):
        async with db.execute("SELECT 1 FROM access_codes WHERE code=?", (code_val,)) as cur:
            if not await cur.fetchone():
                break
        code_val = _new_code()

    await db.execute(
        "INSERT INTO access_codes (id, code, label, permission) VALUES (?,?,?,?)",
        (code_id, code_val, body.label, body.permission),
    )
    await db.commit()

    return CodeOutInternal(
        id=code_id,
        code=code_val,
        label=body.label,
        permission=body.permission,
        created_at=datetime.now(timezone.utc),
        revoked=False,
    )


@router.get("/internal/codes", response_model=list[CodeOutInternal])
async def list_codes_internal():
    db = await get_db()
    async with db.execute(
        """
        SELECT ac.id, ac.code, ac.label, ac.permission, ac.created_at, ac.revoked,
               SUM(CASE WHEN al.action='VIEW'   THEN 1 ELSE 0 END) AS views,
               SUM(CASE WHEN al.action='UPLOAD' THEN 1 ELSE 0 END) AS uploads,
               SUM(CASE WHEN al.action='DELETE' THEN 1 ELSE 0 END) AS deletes,
               MAX(al.timestamp) AS last_seen
        FROM access_codes ac
        LEFT JOIN activity_log al ON al.access_code_id = ac.id
        GROUP BY ac.id
        ORDER BY ac.created_at DESC
        """
    ) as cur:
        rows = await cur.fetchall()

    return [
        CodeOutInternal(
            id=row["id"],
            code=row["code"],
            label=row["label"],
            permission=row["permission"],
            created_at=row["created_at"],
            revoked=bool(row["revoked"]),
            views=row["views"] or 0,
            uploads=row["uploads"] or 0,
            deletes=row["deletes"] or 0,
            last_seen=row["last_seen"],
        )
        for row in rows
    ]


@router.delete("/internal/codes/{code_id}", status_code=204)
async def revoke_code_internal(code_id: str):
    db = await get_db()
    await db.execute("UPDATE access_codes SET revoked=1 WHERE id=?", (code_id,))
    await db.commit()


@router.get("/internal/activity", response_model=list[ActivitySummaryOut])
async def activity_summary():
    db = await get_db()
    async with db.execute(
        """
        SELECT ac.code, ac.label, ac.permission,
               SUM(CASE WHEN al.action='VIEW'   THEN 1 ELSE 0 END) AS views,
               SUM(CASE WHEN al.action='UPLOAD' THEN 1 ELSE 0 END) AS uploads,
               SUM(CASE WHEN al.action='DELETE' THEN 1 ELSE 0 END) AS deletes,
               MAX(al.timestamp) AS last_seen
        FROM access_codes ac
        LEFT JOIN activity_log al ON al.access_code_id = ac.id
        GROUP BY ac.id
        ORDER BY ac.created_at DESC
        """
    ) as cur:
        rows = await cur.fetchall()

    return [
        ActivitySummaryOut(
            code=row["code"],
            label=row["label"],
            permission=row["permission"],
            views=row["views"] or 0,
            uploads=row["uploads"] or 0,
            deletes=row["deletes"] or 0,
            last_seen=row["last_seen"],
        )
        for row in rows
    ]
