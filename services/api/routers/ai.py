"""
AI Editing router — ComfyUI integration
Organiser endpoints (session auth):
  PATCH  /api/events/{code}/ai          → toggle AI editing on/off
  GET    /api/events/{code}/ai/status   → get current job status

Worker endpoints (API key auth):
  GET    /api/ai/queue                  → list QUEUED/IDLE jobs
  POST   /api/ai/jobs/{job_id}/claim    → claim a job (→ PROCESSING)
  POST   /api/ai/jobs/{job_id}/progress → mark one photo done
  POST   /api/ai/jobs/{job_id}/idle     → batch done, waiting for new photos
  POST   /api/ai/jobs/{job_id}/complete → job fully done (toggle off)
  POST   /api/ai/jobs/{job_id}/fail     → report failure
"""
import os
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from db import (
    get_event,
    get_ai_job,
    get_active_ai_job_for_event,
    list_pending_ai_jobs,
    create_ai_job,
    claim_ai_job,
    update_ai_job_progress,
    set_ai_job_idle,
    complete_ai_job,
    fail_ai_job,
    set_ai_job_output_event,
    update_event_ai_state,
)
from middleware import get_current_organiser
from models import (
    AIJobOut,
    AIToggleRequest,
    WorkerCompleteRequest,
    WorkerFailRequest,
    WorkerProgressRequest,
    WorkerIdleRequest,
)

logger = logging.getLogger(__name__)

# Two separate routers so FastAPI doesn't deduplicate when mounted at different prefixes
router = APIRouter(tags=["ai"])          # mounted at /api/events  → /{code}/ai*
worker_router = APIRouter(tags=["ai-worker"])  # mounted at /api/ai     → /worker/*

# ── Available workflows (maps id → display name) ─────────────────────────────
AVAILABLE_WORKFLOWS: dict[str, str] = {
    "seedvr2_upscale": "SeedVR2 4x Upscale",
    # Add more here as you add workflow JSON files to the worker
}


# ── Worker API key auth ───────────────────────────────────────────────────────

def _get_worker_api_key() -> str:
    key = os.getenv("WORKER_API_KEY", "")
    if not key:
        raise RuntimeError("WORKER_API_KEY env var not set on Lambda")
    return key


async def require_worker_key(x_worker_api_key: str = Header(..., alias="X-Worker-Api-Key")):
    """
    Dependency: validates the static API key sent by the local comfy-worker.
    Raises 403 if missing or wrong.
    """
    expected = _get_worker_api_key()
    if x_worker_api_key != expected:
        raise HTTPException(403, "Invalid worker API key")
    return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_out(job: dict) -> AIJobOut:
    return AIJobOut(
        job_id=job["job_id"],
        status=job["status"],
        workflow_id=job["workflow_id"],
        source_event_code=job["source_event_code"],
        output_event_code=job.get("output_event_code") or None,
        created_at=job["created_at"],
        started_at=job.get("started_at") or None,
        completed_at=job.get("completed_at") or None,
        total_photos=int(job.get("total_photos", 0)),
        processed_photos=int(job.get("processed_photos", 0)),
        error=job.get("error") or None,
    )


# ── Organiser: toggle AI editing ──────────────────────────────────────────────

@router.post("/{event_code}/ai")
@router.patch("/{event_code}/ai")
async def toggle_ai_editing(
    event_code: str,
    body: AIToggleRequest,
    organiser: dict = Depends(get_current_organiser),
):
    """
    Enable or disable AI editing for an event.

    Enabling:
      - Validates workflow_id
      - Creates a new AI job (QUEUED) if none active
      - Updates event with ai_editing_enabled=True

    Disabling:
      - Marks the current active job as COMPLETED
      - Updates event with ai_editing_enabled=False
    """
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    if body.enabled:
        # Validate workflow
        workflow_id = body.workflow_id or "seedvr2_upscale"
        if workflow_id not in AVAILABLE_WORKFLOWS:
            raise HTTPException(
                400,
                f"Unknown workflow '{workflow_id}'. Available: {list(AVAILABLE_WORKFLOWS.keys())}"
            )

        # Check for existing active job — don't create a duplicate
        existing_job = await get_active_ai_job_for_event(code)
        if existing_job:
            # Already running with same or different workflow — just update toggle state
            await update_event_ai_state(
                code,
                ai_editing_enabled=True,
                ai_workflow_id=existing_job["workflow_id"],
                ai_job_id=existing_job["job_id"],
            )
            return {
                "message": "AI editing already active",
                "job": _job_out(existing_job),
            }

        # Create a fresh job
        job = await create_ai_job(
            source_event_code=code,
            organiser_email=organiser["email"],
            workflow_id=workflow_id,
        )
        await update_event_ai_state(
            code,
            ai_editing_enabled=True,
            ai_workflow_id=workflow_id,
            ai_job_id=job["job_id"],
        )
        logger.info(f"AI job created: {job['job_id']} for event {code} workflow={workflow_id}")
        return {
            "message": f"AI editing enabled with workflow '{AVAILABLE_WORKFLOWS[workflow_id]}'",
            "job": _job_out(job),
        }

    else:
        # Disabling — find the active job and mark it COMPLETED
        active_job = await get_active_ai_job_for_event(code)
        if active_job:
            await complete_ai_job(
                source_event_code=code,
                job_id=active_job["job_id"],
                output_event_code=active_job.get("output_event_code", ""),
            )

        await update_event_ai_state(code, ai_editing_enabled=False)
        return {"message": "AI editing disabled"}


@router.get("/{event_code}/ai/status")
async def get_ai_status(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    """Return the current AI job status for an event."""
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")

    job = await get_active_ai_job_for_event(code)
    if not job and event.get("ai_job_id"):
        # Fetch last completed/failed job for display
        job = await get_ai_job(code, event["ai_job_id"])

    if not job:
        return {
            "ai_editing_enabled": event.get("ai_editing_enabled", False),
            "job": None,
        }

    return {
        "ai_editing_enabled": event.get("ai_editing_enabled", False),
        "job": _job_out(job),
    }


@router.get("/{event_code}/ai/workflows")
async def list_workflows(
    event_code: str,
    organiser: dict = Depends(get_current_organiser),
):
    """List available AI workflows."""
    code = event_code.upper()
    event = await get_event(code)
    if not event or event.get("organiser_email") != organiser["email"]:
        raise HTTPException(404, "Event not found")
    return [{"id": k, "name": v} for k, v in AVAILABLE_WORKFLOWS.items()]


# ── Worker: queue + job management ────────────────────────────────────────────

@router.get("/worker/queue", dependencies=[Depends(require_worker_key)])
async def worker_get_queue():
    """
    Worker polls this endpoint to find jobs to process.
    Returns QUEUED and IDLE jobs, oldest first.
    Worker must claim a job before processing (prevents double-pick).
    """
    jobs = await list_pending_ai_jobs()
    return [_job_out(j) for j in jobs]


@router.get("/worker/events/{event_code}/photos", dependencies=[Depends(require_worker_key)])
async def worker_list_photos(event_code: str):
    """
    Worker fetches all photos for a source event.
    Returns minimal info needed: id, s3_key, original_name, content_type.
    """
    from db import list_photos as db_list_photos, get_event as db_get_event
    code = event_code.upper()
    event = await db_get_event(code)
    if not event:
        raise HTTPException(404, f"Event {code} not found")
    photos = await db_list_photos(code)
    return [
        {
            "id": p["id"],
            "s3_key": p["s3_key"],
            "original_name": p.get("original_name", "photo.jpg"),
            "content_type": p.get("content_type", "image/jpeg"),
        }
        for p in photos
    ]


@router.post("/worker/jobs/{job_id}/claim", dependencies=[Depends(require_worker_key)])
async def worker_claim_job(job_id: str, request: Request):
    """
    Worker claims a job → sets status PROCESSING.
    Body must contain source_event_code so we can look up the item.
    """
    body = await request.json()
    source_event_code = body.get("source_event_code", "").upper()
    if not source_event_code:
        raise HTTPException(400, "source_event_code required in body")

    job = await get_ai_job(source_event_code, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job["status"] not in ("QUEUED", "IDLE"):
        raise HTTPException(409, f"Job is already in status '{job['status']}', cannot claim")

    await claim_ai_job(source_event_code, job_id)
    return {"message": "Job claimed", "job_id": job_id, "status": "PROCESSING"}


@router.post("/worker/jobs/{job_id}/progress", dependencies=[Depends(require_worker_key)])
async def worker_report_progress(job_id: str, body: WorkerProgressRequest):
    """
    Worker reports one photo processed. Also sets output_event_code if first photo.
    photo_id is added atomically to processed_photo_ids set on the job record.
    """
    # We need source_event_code — worker must also send it
    raise HTTPException(400, "Use /worker/jobs/{job_id}/progress with source_event_code in path")


@router.post(
    "/worker/jobs/{source_event_code}/{job_id}/progress",
    dependencies=[Depends(require_worker_key)],
)
async def worker_report_progress_full(
    source_event_code: str,
    job_id: str,
    body: WorkerProgressRequest,
):
    """
    Worker reports one photo processed. Atomically updates processed_photo_ids set.
    If output_event_code provided (first photo), sets it on the job.
    """
    code = source_event_code.upper()
    job = await get_ai_job(code, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found for event {code}")

    # Set output event code on first photo if provided
    if body.output_event_code and not job.get("output_event_code"):
        await set_ai_job_output_event(code, job_id, body.output_event_code)

    await update_ai_job_progress(code, job_id, body.photo_id, body.total_photos)
    return {"message": "Progress recorded", "photo_id": body.photo_id}


@router.post(
    "/worker/jobs/{source_event_code}/{job_id}/idle",
    dependencies=[Depends(require_worker_key)],
)
async def worker_set_idle(
    source_event_code: str,
    job_id: str,
    body: WorkerIdleRequest,
):
    """
    Worker finished current batch (no new unprocessed photos found).
    Sets status → IDLE so other jobs can run, but this job stays watchable.
    """
    code = source_event_code.upper()
    job = await get_ai_job(code, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found for event {code}")

    if body.output_event_code and not job.get("output_event_code"):
        await set_ai_job_output_event(code, job_id, body.output_event_code)

    await set_ai_job_idle(code, job_id, body.total_photos)
    return {"message": "Job set to IDLE", "job_id": job_id}


@router.post(
    "/worker/jobs/{source_event_code}/{job_id}/complete",
    dependencies=[Depends(require_worker_key)],
)
async def worker_complete_job(
    source_event_code: str,
    job_id: str,
    body: WorkerCompleteRequest,
):
    """Worker signals job is fully done (e.g., event toggle was turned off remotely)."""
    code = source_event_code.upper()
    await complete_ai_job(code, job_id, body.output_event_code)
    return {"message": "Job completed", "job_id": job_id}


@router.post(
    "/worker/jobs/{source_event_code}/{job_id}/fail",
    dependencies=[Depends(require_worker_key)],
)
async def worker_fail_job(
    source_event_code: str,
    job_id: str,
    body: WorkerFailRequest,
):
    """Worker reports a fatal error on a job."""
    code = source_event_code.upper()
    await fail_ai_job(code, job_id, body.error)
    logger.error(f"AI job {job_id} for event {code} failed: {body.error}")
    return {"message": "Job marked failed", "job_id": job_id}
