"""
Auth router — magic link authentication
POST /auth/request   → send magic link
GET  /auth/verify    → consume token, create session, set cookie
POST /auth/logout    → delete session
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse

from db import (
    upsert_organiser,
    create_auth_token,
    invalidate_auth_tokens,
    verify_auth_token,
    mark_token_used,
    create_session,
)
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
    email = body.email.lower()

    # Upsert organiser
    await upsert_organiser(email)

    # Invalidate any existing unused tokens
    await invalidate_auth_tokens(email)

    # Create new token
    token = generate_token(32)
    await create_auth_token(email, token, TOKEN_TTL_MINUTES)

    magic_link = f"{BASE_URL}/auth/verify?token={token}&email={email}"

    try:
        send_magic_link(email, magic_link)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to send magic link: %s", e)
        raise HTTPException(status_code=500, detail="Failed to send email.")

    return MagicLinkResponse(message="Magic link sent — check your email.")


@router.get("/verify")
async def verify_magic_link(token: str, email: str):
    """Consume the magic token and create a session."""
    email = email.lower()

    item = await verify_auth_token(token, email)
    if not item:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")
    if item.get("used"):
        raise HTTPException(status_code=400, detail="This link has already been used.")

    expires_at = datetime.fromisoformat(item["expires_at"])
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")

    # Mark token as used
    await mark_token_used(email, token)

    # Create session
    session_token = generate_token(48)
    await create_session(email, session_token, SESSION_TTL_HOURS)

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
