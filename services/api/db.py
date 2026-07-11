"""
SnapEvent — DynamoDB single-table data layer
All metadata lives in one DynamoDB table using a composite PK/SK pattern.
"""
import os
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

TABLE_NAME = os.getenv("DYNAMODB_TABLE", "snapevent-dev")
_table = None


def _get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb", region_name=os.getenv("S3_REGION", "us-east-1"))
        _table = dynamodb.Table(TABLE_NAME)
    return _table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl_epoch(dt: datetime) -> int:
    """Convert datetime to Unix epoch for DynamoDB TTL."""
    return int(dt.timestamp())


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Organiser Operations ─────────────────────────────────────────────────────

async def upsert_organiser(email: str) -> dict:
    """Create or update organiser profile. Returns the organiser record."""
    table = _get_table()
    item = {
        "PK": f"ORG#{email}",
        "SK": "PROFILE",
        "email": email,
        "created_at": _now_iso(),
    }
    # Use an update to avoid overwriting created_at on existing users
    table.update_item(
        Key={"PK": f"ORG#{email}", "SK": "PROFILE"},
        UpdateExpression="SET email = :e, created_at = if_not_exists(created_at, :c)",
        ExpressionAttributeValues={":e": email, ":c": _now_iso()},
    )
    return {"email": email}


async def get_organiser(email: str) -> Optional[dict]:
    table = _get_table()
    resp = table.get_item(Key={"PK": f"ORG#{email}", "SK": "PROFILE"})
    return resp.get("Item")


# ── Auth Token Operations ────────────────────────────────────────────────────

async def create_auth_token(email: str, token: str, expires_minutes: int = 15) -> None:
    table = _get_table()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    table.put_item(Item={
        "PK": f"ORG#{email}",
        "SK": f"AUTHTOKEN#{token}",
        "token": token,
        "expires_at": expires_at.isoformat(),
        "used": False,
        "ttl_epoch": _ttl_epoch(expires_at + timedelta(hours=1)),  # Auto-cleanup 1hr after expiry
    })


async def invalidate_auth_tokens(email: str) -> None:
    """Mark all unused auth tokens for this organiser as used."""
    table = _get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"ORG#{email}") & Key("SK").begins_with("AUTHTOKEN#"),
    )
    for item in resp.get("Items", []):
        if not item.get("used"):
            table.update_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET used = :t",
                ExpressionAttributeValues={":t": True},
            )


async def verify_auth_token(token: str, email: str) -> Optional[dict]:
    """Verify an auth token. Returns the token item or None."""
    table = _get_table()
    resp = table.get_item(Key={"PK": f"ORG#{email}", "SK": f"AUTHTOKEN#{token}"})
    item = resp.get("Item")
    if not item:
        return None
    return item


async def mark_token_used(email: str, token: str) -> None:
    table = _get_table()
    table.update_item(
        Key={"PK": f"ORG#{email}", "SK": f"AUTHTOKEN#{token}"},
        UpdateExpression="SET used = :t",
        ExpressionAttributeValues={":t": True},
    )


# ── Session Operations ───────────────────────────────────────────────────────

async def create_session(email: str, session_token: str, ttl_hours: int = 720) -> None:
    """Create a login session (default 30 days)."""
    table = _get_table()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    table.put_item(Item={
        "PK": f"ORG#{email}",
        "SK": f"SESSION#{session_token}",
        "token": session_token,
        "email": email,
        "expires_at": expires_at.isoformat(),
        "ttl_epoch": _ttl_epoch(expires_at),
        # GSI for reverse lookup: session_token → email
        "GSI1PK": f"SESSION#{session_token}",
        "GSI1SK": f"ORG#{email}",
    })


async def get_session(session_token: str) -> Optional[dict]:
    """Look up session by token using GSI1."""
    table = _get_table()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"SESSION#{session_token}"),
    )
    items = resp.get("Items", [])
    if not items:
        return None
    return items[0]


async def delete_session(email: str, session_token: str) -> None:
    table = _get_table()
    table.delete_item(Key={"PK": f"ORG#{email}", "SK": f"SESSION#{session_token}"})


# ── Event Operations ─────────────────────────────────────────────────────────

async def create_event(
    email: str,
    event_code: str,
    event_name: str,
    description: Optional[str] = None,
    event_date: Optional[str] = None,
) -> dict:
    """Create an event. Sets expires_at to event_date + 24h or now + 24h."""
    table = _get_table()
    now = datetime.now(timezone.utc)

    # Calculate expiry: event_date + 24h, or now + 24h if no date
    if event_date:
        try:
            event_dt = datetime.fromisoformat(event_date).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            event_dt = now
    else:
        event_dt = now
    expires_at = event_dt + timedelta(hours=24)

    event_item = {
        "PK": f"EVENT#{event_code}",
        "SK": "META",
        "event_code": event_code,
        "event_name": event_name,
        "description": description or "",
        "event_date": event_date or "",
        "organiser_email": email,
        "status": "ACTIVE",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_epoch": _ttl_epoch(expires_at),
        # GSI for organiser → events lookup
        "GSI1PK": f"ORG#{email}",
        "GSI1SK": f"EVENT#{event_code}",
    }
    table.put_item(Item=event_item)

    # Also write a link item under the organiser's PK for easy querying
    table.put_item(Item={
        "PK": f"ORG#{email}",
        "SK": f"EVENT#{event_code}",
        "event_code": event_code,
        "event_name": event_name,
        "created_at": now.isoformat(),
    })

    return event_item


async def get_event(event_code: str) -> Optional[dict]:
    table = _get_table()
    resp = table.get_item(Key={"PK": f"EVENT#{event_code}", "SK": "META"})
    return resp.get("Item")


async def list_organiser_events(email: str) -> list[dict]:
    """List all events for an organiser using GSI1."""
    table = _get_table()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"ORG#{email}") & Key("GSI1SK").begins_with("EVENT#"),
    )
    events = []
    for item in resp.get("Items", []):
        # Fetch full event metadata
        event = await get_event(item["event_code"])
        if event:
            events.append(event)
    return sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)


async def event_code_exists(event_code: str) -> bool:
    event = await get_event(event_code)
    return event is not None


async def event_name_exists_for_organiser(email: str, event_name: str) -> bool:
    events = await list_organiser_events(email)
    return any(e.get("event_name") == event_name for e in events)


async def delete_event_records(event_code: str) -> None:
    """Delete all DynamoDB items for an event (META, access codes, photos, logs)."""
    table = _get_table()

    # Query all items with PK = EVENT#{event_code}
    resp = table.query(KeyConditionExpression=Key("PK").eq(f"EVENT#{event_code}"))
    items = resp.get("Items", [])

    # Also get the organiser link item
    event = await get_event(event_code)

    # Batch delete all event items
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

    # Delete the organiser → event link
    if event and event.get("organiser_email"):
        table.delete_item(Key={
            "PK": f"ORG#{event['organiser_email']}",
            "SK": f"EVENT#{event_code}",
        })


async def get_expired_events() -> list[dict]:
    """Get all events where expires_at < now. Used by cleanup Lambda."""
    table = _get_table()
    now = _now_iso()

    # Scan for EVENT items with expired timestamps
    # Note: For large scale, this should use a GSI. Fine for MVP.
    resp = table.scan(
        FilterExpression="SK = :meta AND expires_at < :now",
        ExpressionAttributeValues={":meta": "META", ":now": now},
    )
    return resp.get("Items", [])


# ── Access Code Operations ───────────────────────────────────────────────────

async def create_access_code(
    event_code: str,
    code: str,
    label: Optional[str],
    permission: str,
) -> dict:
    table = _get_table()
    code_id = _new_id()
    item = {
        "PK": f"EVENT#{event_code}",
        "SK": f"ACCESS#{code}",
        "id": code_id,
        "code": code,
        "label": label or "",
        "permission": permission,
        "created_at": _now_iso(),
        "revoked": False,
    }
    table.put_item(Item=item)
    return item


async def list_access_codes(event_code: str) -> list[dict]:
    table = _get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_code}") & Key("SK").begins_with("ACCESS#"),
    )
    return resp.get("Items", [])


async def get_access_code(event_code: str, code: str) -> Optional[dict]:
    table = _get_table()
    resp = table.get_item(Key={"PK": f"EVENT#{event_code}", "SK": f"ACCESS#{code}"})
    return resp.get("Item")


async def revoke_access_code(event_code: str, code_id: str) -> None:
    """Revoke a code by its ID — find it first then update."""
    codes = await list_access_codes(event_code)
    for c in codes:
        if c["id"] == code_id:
            _get_table().update_item(
                Key={"PK": c["PK"], "SK": c["SK"]},
                UpdateExpression="SET revoked = :t",
                ExpressionAttributeValues={":t": True},
            )
            return


async def validate_participant_code(code: str) -> Optional[dict]:
    """
    Find which event a participant access code belongs to.
    Scans GSI for ACCESS#{code} — acceptable at MVP scale.
    """
    table = _get_table()
    # We need to find the event that has this access code
    # Since we know SK = ACCESS#{code}, we scan for it
    resp = table.scan(
        FilterExpression="SK = :sk AND revoked = :f",
        ExpressionAttributeValues={":sk": f"ACCESS#{code}", ":f": False},
    )
    items = resp.get("Items", [])
    if not items:
        return None
    item = items[0]
    # Extract event_code from PK (EVENT#{code})
    item["event_code"] = item["PK"].replace("EVENT#", "")
    return item


# ── Photo Operations ─────────────────────────────────────────────────────────

async def create_photo_record(
    event_code: str,
    photo_id: str,
    s3_key: str,
    original_name: str,
    content_type: str,
    access_code: str,
) -> dict:
    table = _get_table()
    item = {
        "PK": f"EVENT#{event_code}",
        "SK": f"PHOTO#{photo_id}",
        "id": photo_id,
        "s3_key": s3_key,
        "original_name": original_name,
        "content_type": content_type,
        "uploaded_at": _now_iso(),
        "access_code": access_code,
    }
    table.put_item(Item=item)
    return item


async def list_photos(event_code: str) -> list[dict]:
    table = _get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_code}") & Key("SK").begins_with("PHOTO#"),
    )
    items = resp.get("Items", [])
    return sorted(items, key=lambda p: p.get("uploaded_at", ""), reverse=True)


async def get_photo(event_code: str, photo_id: str) -> Optional[dict]:
    table = _get_table()
    resp = table.get_item(Key={"PK": f"EVENT#{event_code}", "SK": f"PHOTO#{photo_id}"})
    return resp.get("Item")


async def delete_photo_record(event_code: str, photo_id: str) -> None:
    table = _get_table()
    table.delete_item(Key={"PK": f"EVENT#{event_code}", "SK": f"PHOTO#{photo_id}"})


async def count_photos(event_code: str) -> int:
    table = _get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_code}") & Key("SK").begins_with("PHOTO#"),
        Select="COUNT",
    )
    return resp.get("Count", 0)


# ── Activity Log Operations ──────────────────────────────────────────────────

async def log_activity(
    event_code: str,
    access_code: str,
    action: str,
    photo_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    table = _get_table()
    now = _now_iso()
    log_id = _new_id()
    table.put_item(Item={
        "PK": f"EVENT#{event_code}",
        "SK": f"LOG#{now}#{log_id}",
        "access_code": access_code,
        "action": action,
        "photo_id": photo_id or "",
        "ip_address": ip_address or "",
        "timestamp": now,
    })


async def get_activity_summary(event_code: str) -> list[dict]:
    """Get activity summary grouped by access code."""
    table = _get_table()

    # Get all codes and logs for this event
    codes = await list_access_codes(event_code)
    logs_resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_code}") & Key("SK").begins_with("LOG#"),
    )
    logs = logs_resp.get("Items", [])

    # Group logs by access_code
    code_stats = {}
    for code in codes:
        c = code["code"]
        code_stats[c] = {
            "code": c,
            "label": code.get("label", ""),
            "permission": code["permission"],
            "views": 0,
            "uploads": 0,
            "deletes": 0,
            "last_seen": None,
        }

    for log in logs:
        c = log.get("access_code", "")
        if c in code_stats:
            action = log.get("action", "")
            if action == "VIEW":
                code_stats[c]["views"] += 1
            elif action == "UPLOAD":
                code_stats[c]["uploads"] += 1
            elif action == "DELETE":
                code_stats[c]["deletes"] += 1
            ts = log.get("timestamp")
            if ts and (not code_stats[c]["last_seen"] or ts > code_stats[c]["last_seen"]):
                code_stats[c]["last_seen"] = ts

    return list(code_stats.values())
