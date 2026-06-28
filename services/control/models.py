"""
Control Plane — Pydantic schemas
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
    id: str
    event_code: str
    event_name: str
    description: Optional[str]
    event_date: Optional[date]
    status: str
    created_at: datetime
    photo_count: Optional[int] = 0
    code_count: Optional[int] = 0


# ── Access Codes ──────────────────────────────────────────────────────────────

class CodeCreate(BaseModel):
    label: Optional[str] = None
    permission: str  # VIEW_ONLY | VIEW_UPLOAD | VIEW_UPLOAD_DELETE

    class Config:
        use_enum_values = True


class CodeOut(BaseModel):
    id: str
    code: str
    label: Optional[str]
    permission: str
    share_url: str
    created_at: datetime
    revoked: bool
    views: int = 0
    uploads: int = 0
    deletes: int = 0
    last_seen: Optional[datetime] = None


# ── Activity ──────────────────────────────────────────────────────────────────

class ActivitySummary(BaseModel):
    code: str
    label: Optional[str]
    permission: str
    views: int
    uploads: int
    deletes: int
    last_seen: Optional[datetime]
