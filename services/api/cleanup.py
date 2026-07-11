"""
SnapEvent — Cleanup Lambda handler
Runs on an hourly EventBridge schedule.
Finds expired events and deletes their S3 + DynamoDB data.
"""
import logging

from db import get_expired_events, delete_event_records
from storage import delete_event_photos

logger = logging.getLogger(__name__)


def handler(event, context):
    """Lambda entry point — triggered by EventBridge Scheduler."""
    expired = _run_cleanup()
    return {
        "statusCode": 200,
        "body": f"Cleaned up {expired} expired event(s)",
    }


def _run_cleanup() -> int:
    """Synchronous cleanup — Lambda doesn't need async for this."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_cleanup())


async def _async_cleanup() -> int:
    expired_events = await get_expired_events()
    count = 0

    for event in expired_events:
        event_code = event.get("event_code")
        if not event_code:
            continue

        try:
            logger.info("Cleaning up expired event: %s", event_code)

            # 1. Delete all S3 objects under events/{code}/
            await delete_event_photos(event_code)

            # 2. Delete all DynamoDB items (META, ACCESS, PHOTO, LOG)
            await delete_event_records(event_code)

            count += 1
            logger.info("Successfully cleaned up event: %s", event_code)
        except Exception as e:
            logger.error("Failed to clean up event %s: %s", event_code, e)

    if count > 0:
        logger.info("Total events cleaned up: %d", count)

    return count
