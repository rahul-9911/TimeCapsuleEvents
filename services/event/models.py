from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CodeCreateInternal(BaseModel):
    label: Optional[str] = None
    permission: str


class CodeOutInternal(BaseModel):
    id: str
    code: str
    label: Optional[str]
    permission: str
    share_url: str = ""
    created_at: datetime
    revoked: bool
    views: int = 0
    uploads: int = 0
    deletes: int = 0
    last_seen: Optional[datetime] = None


class PhotoOut(BaseModel):
    id: str
    url: str
    download_url: str
    original_name: Optional[str]
    content_type: str
    uploaded_at: datetime
    uploaded_by_label: Optional[str]


class ActivitySummaryOut(BaseModel):
    code: str
    label: Optional[str]
    permission: str
    views: int
    uploads: int
    deletes: int
    last_seen: Optional[datetime]
