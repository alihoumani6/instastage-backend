# utils/storage.py
import os
import io
import time
from typing import Optional

BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()

class StorageBase:
    def save_bytes(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError

# --------------------------
# Local (fallback) storage
# --------------------------
class LocalStorage(StorageBase):
    def __init__(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "media"))
        self.root = root
        os.makedirs(root, exist_ok=True)

    def save_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        # NOTE: this URL assumes you serve /media via FastAPI StaticFiles in main.py (optional)
        return f"/media/{key}"

# --------------------------
# S3 storage
# --------------------------
class S3Storage(StorageBase):
    def __init__(self):
        # Lazy import to avoid boto3 requirement in Local mode
        import boto3
        from botocore.exceptions import ClientError

        self.bucket = os.getenv("AWS_S3_BUCKET")
        if not self.bucket:
            raise RuntimeError("AWS_S3_BUCKET env var is required for S3 backend.")

        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.s3 = boto3.client("s3", region_name=self.region)
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        import botocore
        try:
            # HeadBucket fails if bucket missing or you lack perms
            self.s3.head_bucket(Bucket=self.bucket)
        except self.s3.exceptions.NoSuchBucket:
            self._create_bucket()
        except botocore.exceptions.ClientError as e:
            code = str(e.response.get("Error", {}).get("Code"))
            if code in ("404", "NoSuchBucket"):
                self._create_bucket()
            elif code in ("403", "AccessDenied"):
                # Bucket may exist but you don’t own it / wrong region
                raise RuntimeError(
                    f"S3 bucket '{self.bucket}' not accessible. "
                    "Check region and IAM permissions."
                )
            else:
                raise

    def _create_bucket(self):
        # Special-case: us-east-1 cannot pass LocationConstraint
        if self.region == "us-east-1":
            self.s3.create_bucket(Bucket=self.bucket)
        else:
            self.s3.create_bucket(
                Bucket=self.bucket,
                CreateBucketConfiguration={"LocationConstraint": self.region},
            )

    def save_bytes(self, key: str, data: bytes, content_type: str) -> str:
        # Upload
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        # Return a presigned GET URL (no public bucket needed)
        url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=60 * 60 * 24  # 24 hours
        )
        return url

def get_storage() -> StorageBase:
    if BACKEND == "s3":
        return S3Storage()
    return LocalStorage()
