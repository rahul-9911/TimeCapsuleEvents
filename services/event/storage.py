"""
Event Worker — Storage layer
Abstracts S3 (prod) and MinIO (dev via S3_ENDPOINT override).
"""
import os
import uuid
import boto3
from botocore.config import Config
from typing import Optional

BUCKET = os.getenv("S3_BUCKET", "snapevent-dev")
REGION = os.getenv("S3_REGION", "us-east-1")
ENDPOINT = os.getenv("S3_ENDPOINT")  # None on AWS, http://minio:9000 locally
EVENT_CODE = os.getenv("EVENT_CODE", "UNKNOWN")

_s3 = None


def get_s3():
    global _s3
    if _s3 is None:
        kwargs = dict(
            region_name=REGION,
            config=Config(signature_version="s3v4"),
        )
        if ENDPOINT:
            kwargs["endpoint_url"] = ENDPOINT
        _s3 = boto3.client("s3", **kwargs)
    return _s3


def _key(photo_id: str, filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower() or ".jpg"
    return f"events/{EVENT_CODE}/photos/{photo_id}{ext}"


async def save_photo(data: bytes, original_name: str, content_type: str = "image/jpeg") -> tuple[str, str]:
    """
    Upload photo bytes to S3.
    Returns (photo_id, s3_key).
    """
    photo_id = str(uuid.uuid4())
    s3_key = _key(photo_id, original_name)

    s3 = get_s3()
    s3.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
    return photo_id, s3_key


async def delete_photo(s3_key: str) -> None:
    """Delete a photo from S3."""
    get_s3().delete_object(Bucket=BUCKET, Key=s3_key)


def get_presigned_url(s3_key: str, expires: int = 3600) -> str:
    """Generate a pre-signed GET URL valid for `expires` seconds."""
    return get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": s3_key},
        ExpiresIn=expires,
    )
