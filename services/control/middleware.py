"""
Control Plane — Session auth middleware
"""
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Cookie, HTTPException, Request
from fastapi import status

from db import get_pool


async def get_current_organiser(
    request: Request,
    session_token: Optional[str] = Cookie(default=None, alias="session"),
) -> dict:
    """
    Dependency: validate session cookie and return organiser record.
    Raises 401 if session is missing or expired.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.id, s.organiser_id, s.expires_at,
                   o.email
            FROM sessions s
            JOIN organisers o ON o.id = s.organiser_id
            WHERE s.token = $1
            """,
            session_token,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    return {
        "organiser_id": str(row["organiser_id"]),
        "email": row["email"],
    }


def generate_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)
