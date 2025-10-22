# utils/storage.py
import os, io, mimetypes, time
from typing import Tuple
from uuid import uuid4

DRIVER = os.getenv("STORAGE_DRIVER", "local").lower()
BUCKET = os.getenv("S3_BUCKET")
REGION = os.getenv("AWS_REGION", "us-east-1")
PUBLIC_READ = os.getenv("S3_PUBLIC_READ", "false").lower() == "true"
EXPIRE = int(os.getenv("S3_URL_EXPIRE_SECONDS", "604800"))  # 7d
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")

def _guess_content_type(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"

class Storage:
    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Save and return a fetchable URL."""
        raise NotImplementedError

class LocalStorage(Storage):
    def __init__(self, root: str = "media"):
        self.root = root

    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return f"{PUBLIC_BASE_URL.rstrip('/')}/media/{key}"

class S3Storage(Storage):
    def __init__(self):
        import boto3  # ensure boto3 in requirements
        self.s3 = boto3.client("s3", region_name=REGION)

    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        ct = content_type or _guess_content_type(key)
        extra = {"ContentType": ct}
        if PUBLIC_READ:
            extra["ACL"] = "public-read"
        self.s3.put_object(Bucket=BUCKET, Key=key, Body=data, **extra)
        if PUBLIC_READ:
            # public object URL
            # For us-east-1 (classic), both forms work; this one is region-less:
            return f"https://{BUCKET}.s3.amazonaws.com/{key}"
        # private: return presigned
        return self.s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=EXPIRE,
        )

def get_storage() -> Storage:
    return S3Storage() if DRIVER == "s3" else LocalStorage()
