"""
Control Plane — Access Codes router (organiser-only)
Proxies code management requests to the event container.
"""
import os
import httpx

from fastapi import APIRouter, Depends, HTTPException, Request

from db import get_pool
from middleware import get_current_organiser
from models import CodeCreate, CodeOut, ActivitySummary

router = APIRouter(tags=["codes"])


async def _get_event_url(event_id: str, organiser_id: str) -> str:
    """Look up event internal_url, verify ownership."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT internal_url, status FROM event_registry WHERE id=$1 AND organiser_id=$2",
            event_id,
            organiser_id,
        )
    if not row:
        raise HTTPException(404, "Event not found")
    if row["status"] not in ("RUNNING",):
        raise HTTPException(503, f"Event container is {row['status']} — try again shortly")
    if not row["internal_url"]:
        raise HTTPException(503, "Event container URL not yet available")
    return row["internal_url"]


@router.post("/{event_id}/codes", response_model=CodeOut, status_code=201)
async def create_code(
    event_id: str,
    body: CodeCreate,
    organiser: dict = Depends(get_current_organiser),
):
    if body.permission not in ("VIEW_ONLY", "VIEW_UPLOAD", "VIEW_UPLOAD_DELETE"):
        raise HTTPException(400, "permission must be VIEW_ONLY, VIEW_UPLOAD, or VIEW_UPLOAD_DELETE")

    url = await _get_event_url(event_id, organiser["organiser_id"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{url}/internal/codes",
            json={"label": body.label, "permission": body.permission},
        )
    if resp.status_code != 201:
        raise HTTPException(resp.status_code, resp.text)

    data = resp.json()
    base = os.getenv("BASE_URL", "http://localhost")
    data["share_url"] = f"{base}/e/{data['code']}"
    return CodeOut(**data)


@router.get("/{event_id}/codes", response_model=list[CodeOut])
async def list_codes(
    event_id: str,
    organiser: dict = Depends(get_current_organiser),
):
    url = await _get_event_url(event_id, organiser["organiser_id"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{url}/internal/codes")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)

    base = os.getenv("BASE_URL", "http://localhost")
    items = resp.json()
    for item in items:
        item["share_url"] = f"{base}/e/{item['code']}"
    return [CodeOut(**item) for item in items]


@router.delete("/{event_id}/codes/{code_id}", status_code=204)
async def revoke_code(
    event_id: str,
    code_id: str,
    organiser: dict = Depends(get_current_organiser),
):
    url = await _get_event_url(event_id, organiser["organiser_id"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(f"{url}/internal/codes/{code_id}")
    if resp.status_code not in (204, 404):
        raise HTTPException(resp.status_code, resp.text)


@router.get("/{event_id}/activity", response_model=list[ActivitySummary])
async def get_activity(
    event_id: str,
    organiser: dict = Depends(get_current_organiser),
):
    url = await _get_event_url(event_id, organiser["organiser_id"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{url}/internal/activity")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)

    return [ActivitySummary(**item) for item in resp.json()]
