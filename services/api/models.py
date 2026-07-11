"""
SnapEvent — Pydantic schemas (merged from control + event models)
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, datetime


# ── Auth ─────────────────────────────────────────────────────────────────────

class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    message: str


# ── Events ───────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    event_name: str
    description: Optional[str] = None
    event_date: Optional[date] = None


class EventOut(BaseModel):
    event_code: str
    event_name: str
    description: Optional[str] = None
    event_date: Optional[str] = None
    status: str
    created_at: str
    expires_at: Optional[str] = None
    photo_count: int = 0
    code_count: int = 0


# ── Access Codes ──────────────────────────────────────────────────────────────

class CodeCreate(BaseModel):
    label: Optional[str] = None
    permission: str  # VIEW_ONLY | VIEW_UPLOAD | VIEW_UPLOAD_DELETE


class CodeOut(BaseModel):
    id: str
    code: str
    label: Optional[str] = None
    permission: str
    share_url: str = ""
    created_at: str
    revoked: bool = False
    views: int = 0
    uploads: int = 0
    deletes: int = 0
    last_seen: Optional[str] = None


# ── Photos ───────────────────────────────────────────────────────────────────

class PhotoOut(BaseModel):
    id: str
    url: str
    download_url: str
    original_name: Optional[str] = None
    content_type: str = "image/jpeg"
    uploaded_at: str
    uploaded_by_label: Optional[str] = None


# ── Activity ──────────────────────────────────────────────────────────────────

class ActivitySummary(BaseModel):
    code: str
    label: Optional[str] = None
    permission: str
    views: int = 0
    uploads: int = 0
    deletes: int = 0
    last_seen: Optional[str] = None
