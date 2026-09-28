"""
main.py — SnapEvent ComfyUI Worker

Polls the SnapEvent API for AI editing jobs, processes them through
a local ComfyUI instance, and uploads results back to S3.

Usage:
    python main.py

Environment (see .env.example):
    SNAPEVENT_API_URL       Base URL of SnapEvent API (no trailing slash)
    WORKER_API_KEY          Static API key (must match WORKER_API_KEY on Lambda)
    S3_BUCKET               S3 bucket name
    AWS_REGION              AWS region
    COMFYUI_URL             ComfyUI base URL (default: http://localhost:8188)
    COMFYUI_INPUT_DIR       Path to ComfyUI's input/ folder
    COMFYUI_OUTPUT_DIR      Path to ComfyUI's output/ folder
    POLL_INTERVAL_SECONDS   How often to poll for new jobs (default: 30)
    COMFY_POLL_INTERVAL     How often to poll ComfyUI completion (default: 3.0)
    COMFY_TIMEOUT           Max seconds to wait for one image (default: 600)
    LOG_LEVEL               Logging level (default: INFO)
"""
import logging
import os
import sys
import time
import tempfile
import uuid
from pathlib import Path

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("comfy-worker")

# ── Config ────────────────────────────────────────────────────────────────────
SNAPEVENT_API_URL    = os.getenv("SNAPEVENT_API_URL", "").rstrip("/")
WORKER_API_KEY       = os.getenv("WORKER_API_KEY", "")
S3_BUCKET            = os.getenv("S3_BUCKET", "")
AWS_REGION           = os.getenv("AWS_REGION", "ap-south-1")
COMFYUI_URL          = os.getenv("COMFYUI_URL", "http://localhost:8188")
COMFYUI_INPUT_DIR    = Path(os.getenv("COMFYUI_INPUT_DIR", "/home/rahul/comfy/ComfyUI/input"))
COMFYUI_OUTPUT_DIR   = Path(os.getenv("COMFYUI_OUTPUT_DIR", "/home/rahul/comfy/ComfyUI/output"))
POLL_INTERVAL        = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
COMFY_POLL_INTERVAL  = float(os.getenv("COMFY_POLL_INTERVAL", "3.0"))
COMFY_TIMEOUT        = float(os.getenv("COMFY_TIMEOUT", "600.0"))

WORKFLOWS_DIR = Path(__file__).parent / "workflows"

# Map workflow_id → JSON filename in workflows/
WORKFLOW_FILES: dict[str, str] = {
    "seedvr2_upscale": "seedvr2_upscale.json",
    # Add more as you add workflow JSON files
}


def _validate_config():
    missing = []
    if not SNAPEVENT_API_URL:
        missing.append("SNAPEVENT_API_URL")
    if not WORKER_API_KEY:
        missing.append("WORKER_API_KEY")
    if not S3_BUCKET:
        missing.append("S3_BUCKET")
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    if not COMFYUI_INPUT_DIR.exists():
        logger.error(f"COMFYUI_INPUT_DIR does not exist: {COMFYUI_INPUT_DIR}")
        sys.exit(1)
    if not COMFYUI_OUTPUT_DIR.exists():
        logger.error(f"COMFYUI_OUTPUT_DIR does not exist: {COMFYUI_OUTPUT_DIR}")
        sys.exit(1)


# ── Lazy imports (after config validated) ─────────────────────────────────────
from comfy_client import ComfyClient
from s3_client import S3Client
from api_client import SnapEventAPIClient


# ── Worker core ───────────────────────────────────────────────────────────────

def process_job(
    job: dict,
    comfy: ComfyClient,
    s3: S3Client,
    api: SnapEventAPIClient,
) -> None:
    """
    Process one AI job:
      1. Fetch all photos for the source event
      2. Compute todo = all_photos - already_processed
      3. For each unprocessed photo:
         a. Download from S3
         b. Run through ComfyUI workflow
         c. Upload result to S3 under output event
         d. Create photo record in output event via DynamoDB (via API progress endpoint)
         e. Mark photo done (atomic update to processed_photo_ids)
      4. Set job IDLE when batch done

    The output event is auto-created on the first photo by the API's progress endpoint.
    """
    job_id              = job["job_id"]
    source_event_code   = job["source_event_code"]
    workflow_id         = job["workflow_id"]
    already_processed   = set(job.get("processed_photo_ids", []) or [])
    output_event_code   = job.get("output_event_code") or None

    logger.info(
        f"Processing job {job_id} | event={source_event_code} | "
        f"workflow={workflow_id} | already_done={len(already_processed)}"
    )

    # ── Validate workflow ─────────────────────────────────────────────────────
    if workflow_id not in WORKFLOW_FILES:
        raise ValueError(f"Unknown workflow_id '{workflow_id}'. "
                         f"Available: {list(WORKFLOW_FILES.keys())}")

    workflow_path = WORKFLOWS_DIR / WORKFLOW_FILES[workflow_id]
    if not workflow_path.exists():
        raise FileNotFoundError(
            f"Workflow file not found: {workflow_path}. "
            f"Copy {workflow_id}.json to the workflows/ directory."
        )

    # ── Fetch photos from the API ─────────────────────────────────────────────
    headers = {"X-Worker-Api-Key": WORKER_API_KEY}
    photos_url = f"{SNAPEVENT_API_URL}/api/ai/worker/events/{source_event_code}/photos"
    resp = requests.get(photos_url, headers=headers, timeout=30)
    resp.raise_for_status()
    all_photos = resp.json()  # list of {id, s3_key, original_name, content_type}

    todo = [p for p in all_photos if p["id"] not in already_processed]
    total_photos = len(all_photos)

    logger.info(
        f"Job {job_id}: {len(all_photos)} total photos, "
        f"{len(already_processed)} done, {len(todo)} to process"
    )

    if not todo:
        logger.info(f"Job {job_id}: no new photos to process → setting IDLE")
        api.set_idle(source_event_code, job_id, total_photos, output_event_code)
        return

    # ── Process each photo ────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="snapevent_worker_") as tmpdir:
        tmp_path = Path(tmpdir)

        for photo in todo:
            photo_id      = photo["id"]
            s3_key        = photo["s3_key"]
            original_name = photo.get("original_name") or Path(s3_key).name
            content_type  = photo.get("content_type", "image/jpeg")

            logger.info(f"  Processing photo {photo_id} ({original_name})")

            try:
                # 1. Download from S3
                local_input = s3.download_photo(s3_key, tmp_path)

                # 2. Run through ComfyUI
                output_paths = comfy.run_workflow(
                    workflow_path=workflow_path,
                    image_path=local_input,
                    original_name=original_name,
                )

                if not output_paths:
                    raise RuntimeError("ComfyUI returned no output files")

                # Use first output (upscale workflows produce one output)
                output_path = output_paths[0]

                # 3. Upload to S3 under output event
                output_photo_id = str(uuid.uuid4())
                output_ext = output_path.suffix.lower() or ".png"
                # Determine content type from extension
                output_content_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(output_ext, "image/png")

                output_s3_key = s3.upload_photo(
                    local_path=output_path,
                    output_event_code=output_event_code or "PENDING",
                    photo_id=output_photo_id,
                    content_type=output_content_type,
                )

                # 4. Report progress to API
                # On first photo, output_event_code is None — API will create the event
                # and return the code. We pass None and the API handles creation.
                api.report_progress(
                    source_event_code=source_event_code,
                    job_id=job_id,
                    photo_id=photo_id,
                    total_photos=total_photos,
                    output_event_code=output_event_code,
                )

                # Clean up local output file
                try:
                    output_path.unlink(missing_ok=True)
                    local_input.unlink(missing_ok=True)
                except Exception:
                    pass

                logger.info(f"  ✓ Photo {photo_id} done → {output_s3_key}")

            except Exception as e:
                logger.error(f"  ✗ Photo {photo_id} failed: {e}", exc_info=True)
                # Don't fail the whole job for one photo — skip and continue
                # The photo_id is NOT added to processed_photo_ids, so it will retry
                continue

    # ── All photos in this batch done ─────────────────────────────────────────
    logger.info(f"Job {job_id}: batch complete → setting IDLE (watching for new photos)")
    api.set_idle(source_event_code, job_id, total_photos, output_event_code)


def check_comfyui_health(comfyui_url: str) -> bool:
    """Returns True if ComfyUI is reachable and idle."""
    try:
        resp = requests.get(f"{comfyui_url}/system_stats", timeout=5)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"ComfyUI health check failed: {e}")
        return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    _validate_config()

    comfy = ComfyClient(
        base_url=COMFYUI_URL,
        input_dir=str(COMFYUI_INPUT_DIR),
        output_dir=str(COMFYUI_OUTPUT_DIR),
        poll_interval=COMFY_POLL_INTERVAL,
        timeout=COMFY_TIMEOUT,
    )
    s3 = S3Client(bucket=S3_BUCKET, region=AWS_REGION)
    api = SnapEventAPIClient(base_url=SNAPEVENT_API_URL, api_key=WORKER_API_KEY)

    logger.info("=" * 60)
    logger.info("  SnapEvent ComfyUI Worker starting")
    logger.info(f"  API: {SNAPEVENT_API_URL}")
    logger.info(f"  ComfyUI: {COMFYUI_URL}")
    logger.info(f"  S3 bucket: {S3_BUCKET}")
    logger.info(f"  Poll interval: {POLL_INTERVAL}s")
    logger.info(f"  Workflows dir: {WORKFLOWS_DIR}")
    logger.info("=" * 60)

    # Initial ComfyUI health check
    if not check_comfyui_health(COMFYUI_URL):
        logger.error("ComfyUI is not reachable. Is it running?")
        sys.exit(1)
    logger.info("ComfyUI health check OK ✓")

    while True:
        try:
            # ── Poll for jobs ─────────────────────────────────────────────────
            jobs = api.get_queue()

            if not jobs:
                logger.debug(f"No pending jobs. Sleeping {POLL_INTERVAL}s…")
                time.sleep(POLL_INTERVAL)
                continue

            # Only take the first job (FIFO, one at a time)
            job = jobs[0]
            job_id            = job["job_id"]
            source_event_code = job["source_event_code"]

            logger.info(
                f"Found job {job_id} | event={source_event_code} | "
                f"status={job['status']} | workflow={job['workflow_id']}"
            )

            # ── Claim it ──────────────────────────────────────────────────────
            claimed = api.claim_job(job_id, source_event_code)
            if not claimed:
                logger.warning(f"Could not claim job {job_id} (already taken?), skipping")
                time.sleep(5)
                continue

            # ── Verify ComfyUI is still up ────────────────────────────────────
            if not check_comfyui_health(COMFYUI_URL):
                logger.error("ComfyUI went offline during job. Failing job.")
                api.fail_job(source_event_code, job_id, "ComfyUI is not reachable")
                time.sleep(POLL_INTERVAL)
                continue

            # ── Process ───────────────────────────────────────────────────────
            try:
                process_job(job, comfy, s3, api)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
                api.fail_job(source_event_code, job_id, error_msg[:500])

            # Small delay between jobs to let ComfyUI breathe
            time.sleep(5)

        except KeyboardInterrupt:
            logger.info("Shutdown requested. Exiting.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
