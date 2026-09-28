"""
api_client.py — SnapEvent API client for the comfy-worker

All communication with the SnapEvent cloud API goes through this class.
Authenticates via X-Worker-Api-Key header.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SnapEventAPIClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-Worker-Api-Key": api_key,
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=body, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _get(self, path: str) -> list | dict:
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── Queue / Job lifecycle ─────────────────────────────────────────────────

    def get_queue(self) -> list[dict]:
        """Fetch list of QUEUED and IDLE jobs from the API."""
        try:
            result = self._get("/api/ai/worker/queue")
            return result if isinstance(result, list) else []
        except requests.HTTPError as e:
            logger.error(f"Failed to fetch queue: {e}")
            return []

    def claim_job(self, job_id: str, source_event_code: str) -> bool:
        """Claim a job → PROCESSING. Returns True on success."""
        try:
            self._post(
                f"/api/ai/worker/jobs/{job_id}/claim",
                {"source_event_code": source_event_code},
            )
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to claim job {job_id}: {e}")
            return False

    def report_progress(
        self,
        source_event_code: str,
        job_id: str,
        photo_id: str,
        total_photos: int,
        output_event_code: Optional[str] = None,
        output_photo_id: Optional[str] = None,
        output_s3_key: Optional[str] = None,
        original_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> dict:
        """
        Report one photo processed. Atomically updates DynamoDB processed_photo_ids set.
        Returns response dict containing updated output_event_code.
        """
        try:
            body: dict = {"photo_id": photo_id, "total_photos": total_photos}
            if output_event_code:
                body["output_event_code"] = output_event_code
            if output_photo_id:
                body["output_photo_id"] = output_photo_id
            if output_s3_key:
                body["output_s3_key"] = output_s3_key
            if original_name:
                body["original_name"] = original_name
            if content_type:
                body["content_type"] = content_type

            resp = self._post(
                f"/api/ai/worker/jobs/{source_event_code}/{job_id}/progress",
                body,
            )
            return resp if isinstance(resp, dict) else {}
        except requests.HTTPError as e:
            logger.error(f"Failed to report progress for job {job_id}: {e}")
            return {}

    def set_idle(
        self,
        source_event_code: str,
        job_id: str,
        total_photos: int,
        output_event_code: Optional[str] = None,
    ) -> bool:
        """Notify API that current batch is done, job goes IDLE (watching for new photos)."""
        try:
            body: dict = {"total_photos": total_photos}
            if output_event_code:
                body["output_event_code"] = output_event_code
            self._post(
                f"/api/ai/worker/jobs/{source_event_code}/{job_id}/idle",
                body,
            )
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to set job {job_id} idle: {e}")
            return False

    def complete_job(
        self,
        source_event_code: str,
        job_id: str,
        output_event_code: str,
    ) -> bool:
        """Mark a job COMPLETED (rare — usually done by organiser toggling off)."""
        try:
            self._post(
                f"/api/ai/worker/jobs/{source_event_code}/{job_id}/complete",
                {"output_event_code": output_event_code},
            )
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to complete job {job_id}: {e}")
            return False

    def fail_job(self, source_event_code: str, job_id: str, error: str) -> bool:
        """Report a fatal error on a job."""
        try:
            self._post(
                f"/api/ai/worker/jobs/{source_event_code}/{job_id}/fail",
                {"error": error},
            )
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to report failure for job {job_id}: {e}")
            return False

    # ── Event management (for creating output event) ──────────────────────────

    def create_output_event(
        self,
        organiser_email: str,
        source_event_name: str,
        workflow_name: str,
        retention_days: int,
        session_cookie: Optional[str] = None,
    ) -> Optional[str]:
        """
        NOTE: Creating an event requires organiser session auth, not the worker API key.
        The worker cannot directly create events — it reports progress to the API,
        and the API creates the output event on the first photo.

        This method is kept as a placeholder for reference.
        Output event creation is handled server-side in the API.
        """
        raise NotImplementedError(
            "Output event creation is handled by the API, not the worker. "
            "Pass output_event_code=None on first progress call and the API creates it."
        )
