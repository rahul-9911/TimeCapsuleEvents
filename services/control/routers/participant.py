"""
Control Plane — Participant discovery endpoint
Lets the gallery page resolve event_code from a participant access code.
"""
from fastapi import APIRouter, HTTPException, Request
import httpx

from db import get_pool

router = APIRouter(tags=["participant"])


@router.post("/api/participant/discover")
async def discover_event(request: Request):
    """
    Given an X-Participant-Code header, return the event_code + permission level.
    This is how the gallery page bootstraps without knowing the event URL in advance.
    """
    participant_code = request.headers.get("X-Participant-Code")
    if not participant_code:
        raise HTTPException(401, "X-Participant-Code header required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Find the event that has a running container with this code
        # We probe each running event's internal_url
        rows = await conn.fetch(
            "SELECT event_code, internal_url FROM event_registry WHERE status = 'RUNNING' AND internal_url IS NOT NULL"
        )

    # Try each running event container to find which one knows this code
    for row in rows:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{row['internal_url']}/internal/codes",
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    codes = resp.json()
                    for code in codes:
                        if code["code"] == participant_code.upper() and not code["revoked"]:
                            return {
                                "event_code": row["event_code"],
                                "permission": code["permission"],
                                "label": code.get("label"),
                            }
        except Exception:
            continue

    raise HTTPException(403, "Access code not found or revoked")
