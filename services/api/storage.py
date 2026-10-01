"""
SnapEvent — S3 storage layer
Single bucket with events/{code}/photos/ prefix structure.
Handles photo upload, delete, presigned URL generation, and thumbnail creation.
"""
import io
import os
import uuid
import logging

import boto3
from botocore.config import Config
from PIL import Image

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 400
THUMBNAIL_QUALITY = 80

BUCKET = os.getenv("S3_BUCKET", "snapevent-dev-photos")
REGION = os.getenv("S3_REGION", "us-east-1")

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            region_name=REGION,
            endpoint_url=f"https://s3.{REGION}.amazonaws.com",
            config=Config(signature_version="s3v4"),
        )
    return _s3


def _photo_key(event_code: str, photo_id: str, filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower() or ".jpg"
    return f"events/{event_code}/photos/{photo_id}{ext}"


def _thumb_key(event_code: str, photo_id: str) -> str:
    """Thumbnail S3 key — always JPEG."""
    return f"events/{event_code}/thumbs/{photo_id}.jpg"


async def save_photo(
    event_code: str,
    data: bytes,
    original_name: str,
    content_type: str = "image/jpeg",
) -> tuple[str, str]:
    """
    Upload photo bytes to S3.
    Returns (photo_id, s3_key).
    """
    photo_id = str(uuid.uuid4())
    s3_key = _photo_key(event_code, photo_id, original_name)

    s3 = _get_s3()
    s3.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
    return photo_id, s3_key


async def delete_photo(s3_key: str) -> None:
    """Delete a single photo from S3."""
    _get_s3().delete_object(Bucket=BUCKET, Key=s3_key)


def get_presigned_url(
    s3_key: str,
    expires: int = 3600,
    download_filename: str = None,
) -> str:
    """Generate a presigned GET URL valid for `expires` seconds."""
    params = {"Bucket": BUCKET, "Key": s3_key}
    if download_filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_filename}"'

    return _get_s3().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires,
    )


def generate_presigned_post(
    event_code: str,
    filename: str,
    content_type: str,
    max_size_mb: int = 50,
) -> tuple[str, str, dict]:
    """
    Generate a presigned POST URL for direct browser uploads.
    Returns (photo_id, s3_key, presigned_post_data_dict)
    """
    photo_id = str(uuid.uuid4())
    s3_key = _photo_key(event_code, photo_id, filename)

    s3 = _get_s3()
    
    conditions = [
        ["starts-with", "$Content-Type", ""],
        ["content-length-range", 0, max_size_mb * 1024 * 1024],
    ]

    # Boto3 generates a dictionary with 'url' and 'fields'
    presigned_data = s3.generate_presigned_post(
        Bucket=BUCKET,
        Key=s3_key,
        Fields={"Content-Type": content_type},
        Conditions=conditions,
        ExpiresIn=3600,
    )

    return photo_id, s3_key, presigned_data


async def generate_thumbnail(event_code: str, photo_id: str, s3_key: str) -> str | None:
    """
    Download the original photo from S3, resize to THUMBNAIL_WIDTH px wide,
    save as JPEG, and upload to the thumbs/ prefix.
    Returns the thumbnail S3 key, or None on failure.
    """
    s3 = _get_s3()
    thumb_s3_key = _thumb_key(event_code, photo_id)

    try:
        # Download original
        resp = s3.get_object(Bucket=BUCKET, Key=s3_key)
        original_bytes = resp["Body"].read()

        # Open and resize
        img = Image.open(io.BytesIO(original_bytes))
        img = img.convert("RGB")  # Ensure JPEG-compatible (handles RGBA, P, etc.)

        # Calculate height preserving aspect ratio
        w, h = img.size
        if w <= THUMBNAIL_WIDTH:
            # Image is already small enough — still make a JPEG copy for consistency
            thumb = img
        else:
            ratio = THUMBNAIL_WIDTH / w
            thumb = img.resize((THUMBNAIL_WIDTH, int(h * ratio)), Image.LANCZOS)

        # Save to buffer
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
        buf.seek(0)

        # Upload thumbnail
        s3.put_object(
            Bucket=BUCKET,
            Key=thumb_s3_key,
            Body=buf.getvalue(),
            ContentType="image/jpeg",
        )

        logger.info("Thumbnail generated: %s (%dx%d -> %dx%d)",
                    thumb_s3_key, w, h, thumb.size[0], thumb.size[1])
        return thumb_s3_key

    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", s3_key, e)
        return None


def get_thumbnail_url(event_code: str, photo_id: str, expires: int = 3600) -> str | None:
    """Generate a presigned GET URL for a thumbnail. Returns None if the key doesn't exist."""
    thumb_key = _thumb_key(event_code, photo_id)
    try:
        return _get_s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": thumb_key},
            ExpiresIn=expires,
        )
    except Exception:
        return None


async def delete_event_photos(event_code: str) -> None:
    """Delete all S3 objects under an event's prefix (includes photos + thumbs)."""
    s3 = _get_s3()
    prefix = f"events/{event_code}/"

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        if "Contents" in page:
            objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
            if objects:
                s3.delete_objects(
                    Bucket=BUCKET,
                    Delete={"Objects": objects},
                )
