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
    retention_days: Optional[int] = 2


class EventOut(BaseModel):
    event_code: str
    event_name: str
    description: Optional[str] = None
    event_date: Optional[str] = None
    retention_days: Optional[int] = 2
    status: str
    created_at: str
    expires_at: Optional[str] = None
    photo_count: int = 0
    code_count: int = 0
    # AI editing fields
    ai_editing_enabled: bool = False
    ai_workflow_id: Optional[str] = None
    ai_job_id: Optional[str] = None
    ai_job_status: Optional[str] = None       # QUEUED|PROCESSING|IDLE|COMPLETED|FAILED
    ai_job_progress: Optional[dict] = None    # {processed, total}
    ai_output_event_code: Optional[str] = None


# ── Access Codes ──────────────────────────────────────────────────────────────

class CodeCreate(BaseModel):
    label: Optional[str] = None
    permission: str  # VIEW_ONLY | VIEW_UPLOAD | VIEW_UPLOAD_DELETE
    allow_bulk_download: bool = True
    allow_ai_trigger: bool = False  # Can this code enable/disable AI editing toggle


class CodeOut(BaseModel):
    id: str
    code: str
    label: Optional[str] = None
    permission: str
    allow_bulk_download: bool = True
    allow_ai_trigger: bool = False
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
    uploaded_at: Optional[str] = None
    uploaded_by_label: Optional[str] = None


class BatchDeleteRequest(BaseModel):
    photo_ids: list[str]


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str


class UploadConfirmRequest(BaseModel):
    photo_id: str
    s3_key: str
    original_name: str
    content_type: str


# ── Activity ──────────────────────────────────────────────────────────────────

class ActivitySummary(BaseModel):
    code: str
    label: Optional[str] = None
    permission: str
    views: int = 0
    uploads: int = 0
    deletes: int = 0
    last_seen: Optional[str] = None


# ── AI Editing ───────────────────────────────────────────────────────────────

class AIToggleRequest(BaseModel):
    enabled: bool
    workflow_id: Optional[str] = "seedvr2_upscale"  # default workflow


class AIJobOut(BaseModel):
    job_id: str
    status: str                      # QUEUED|PROCESSING|IDLE|COMPLETED|FAILED
    workflow_id: str
    source_event_code: str
    output_event_code: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_photos: int = 0
    processed_photos: int = 0
    error: Optional[str] = None


class WorkerCompleteRequest(BaseModel):
    output_event_code: str


class WorkerFailRequest(BaseModel):
    error: str


class WorkerProgressRequest(BaseModel):
    photo_id: str
    total_photos: int
    output_event_code: Optional[str] = None  # set on first photo if not already set


class WorkerIdleRequest(BaseModel):
    total_photos: int
    output_event_code: Optional[str] = None
