"""
SnapEvent — Session auth middleware (DynamoDB-backed)
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Cookie, HTTPException, Request, status

from db import get_session


async def get_current_organiser(
    request: Request,
    session_token: Optional[str] = Cookie(default=None, alias="session"),
) -> dict:
    """
    Dependency: validate session cookie and return organiser info.
    Raises 401 if session is missing or expired.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session = await get_session(session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    expires_at = datetime.fromisoformat(session["expires_at"])
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    return {
        "email": session["email"],
    }


def generate_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)
