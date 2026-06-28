"""
Control Plane — Auth router
POST /auth/request   → send magic link
GET  /auth/verify    → consume token, create session, set cookie
POST /auth/logout    → delete session
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse

from db import get_pool
from mailer import send_magic_link
from middleware import generate_token
from models import MagicLinkRequest, MagicLinkResponse

router = APIRouter(tags=["auth"])

BASE_URL = os.getenv("BASE_URL", "http://localhost")
TOKEN_TTL_MINUTES = 15
SESSION_TTL_HOURS = 24 * 30  # 30 days


@router.post("/request", response_model=MagicLinkResponse)
async def request_magic_link(body: MagicLinkRequest):
    """Create organiser if new, then send a magic link to their email."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Upsert organiser
        organiser = await conn.fetchrow(
            """
            INSERT INTO organisers (email) VALUES ($1)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id, email
            """,
            body.email,
        )

        # Invalidate any existing unused tokens for this organiser
        await conn.execute(
            "UPDATE auth_tokens SET used = TRUE WHERE organiser_id = $1 AND used = FALSE",
            organiser["id"],
        )

        # Create new token
        token = generate_token(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
        await conn.execute(
            "INSERT INTO auth_tokens (organiser_id, token, expires_at) VALUES ($1, $2, $3)",
            organiser["id"],
            token,
            expires_at,
        )

    magic_link = f"{BASE_URL}/auth/verify?token={token}"

    try:
        send_magic_link(body.email, magic_link)
    except Exception as e:
        # Log but don't expose SMTP errors to caller
        import logging
        logging.getLogger(__name__).error("Failed to send magic link: %s", e)
        raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP config.")

    return MagicLinkResponse(message="Magic link sent — check your email.")


@router.get("/verify")
async def verify_magic_link(token: str, response: Response):
    """Consume the magic token and create a session."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, organiser_id, expires_at, used
            FROM auth_tokens
            WHERE token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired link.")
        if row["used"]:
            raise HTTPException(status_code=400, detail="This link has already been used.")
        if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")

        # Mark token as used
        await conn.execute("UPDATE auth_tokens SET used = TRUE WHERE id = $1", row["id"])

        # Create session
        session_token = generate_token(48)
        session_expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        await conn.execute(
            "INSERT INTO sessions (organiser_id, token, expires_at) VALUES ($1, $2, $3)",
            row["organiser_id"],
            session_token,
            session_expires,
        )

    redirect = RedirectResponse(url="/dashboard.html", status_code=302)
    redirect.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        secure=os.getenv("ENV", "dev") != "dev",
    )
    return redirect


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"message": "Logged out"}
