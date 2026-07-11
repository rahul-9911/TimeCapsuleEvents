"""
SnapEvent — S3 storage layer
Single bucket with events/{code}/photos/ prefix structure.
Handles photo upload, delete, and presigned URL generation.
"""
import os
import uuid

import boto3
from botocore.config import Config

BUCKET = os.getenv("S3_BUCKET", "snapevent-dev-photos")
REGION = os.getenv("S3_REGION", "us-east-1")

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            region_name=REGION,
            config=Config(signature_version="s3v4"),
        )
    return _s3


def _photo_key(event_code: str, photo_id: str, filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower() or ".jpg"
    return f"events/{event_code}/photos/{photo_id}{ext}"


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


async def delete_event_photos(event_code: str) -> None:
    """Delete all S3 objects under an event's prefix."""
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
