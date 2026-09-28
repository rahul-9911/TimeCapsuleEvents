"""
s3_client.py — S3 download/upload helpers for the comfy-worker

Download: pulls original photos from S3 to a local temp directory.
Upload:   pushes edited output files back to S3 under the output event prefix.
"""
import logging
import os
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)


class S3Client:
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.region = region
        self._s3 = boto3.client(
            "s3",
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def download_photo(self, s3_key: str, dest_dir: Path) -> Path:
        """
        Download one photo from S3 to dest_dir.
        Returns the local Path to the downloaded file.
        """
        filename = Path(s3_key).name
        local_path = dest_dir / filename
        logger.debug(f"Downloading s3://{self.bucket}/{s3_key} → {local_path}")
        self._s3.download_file(self.bucket, s3_key, str(local_path))
        return local_path

    def upload_photo(
        self,
        local_path: Path,
        output_event_code: str,
        photo_id: str,
        content_type: str = "image/png",
    ) -> str:
        """
        Upload an edited photo to S3 under the output event's prefix.
        Key pattern: events/{output_event_code}/photos/{photo_id}{ext}

        Returns the S3 key.
        """
        ext = local_path.suffix.lower() or ".png"
        s3_key = f"events/{output_event_code}/photos/{photo_id}{ext}"
        logger.debug(f"Uploading {local_path} → s3://{self.bucket}/{s3_key}")
        self._s3.upload_file(
            str(local_path),
            self.bucket,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
        return s3_key
