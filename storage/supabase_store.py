# storage/supabase_store.py
import os
import time
import uuid
from typing import Optional, Tuple

from supabase import create_client, Client


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "1" if default else "0").strip()
    return v in ("1", "true", "True", "YES", "yes")


def _mime_for(ext: str) -> str:
    e = ext.lower().lstrip(".")
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "webp": "image/webp",
    }.get(e, "application/octet-stream")


class SupabaseStorage:
    def __init__(self):
        self.enabled = _bool_env("USE_SUPABASE", False)
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_ANON_KEY")
        self.bucket = os.getenv("SUPABASE_BUCKET", "instastage").strip()
        self.prefix = (os.getenv("SUPA_PREFIX") or "instastage").strip().strip("/")
        self.expires = int(os.getenv("SUPA_URL_EXPIRES", "604800"))  # 7 days
        self.client: Optional[Client] = None

        if self.enabled:
            if not (self.url and self.key):
                raise RuntimeError("Supabase storage enabled but SUPABASE_URL or SUPABASE_ANON_KEY missing")
            self.client = create_client(self.url, self.key)

    def key_for(self, kind: str, ext: str) -> str:
        uid = str(uuid.uuid4())
        day = time.strftime('%Y/%m/%d')
        return f"{self.prefix}/{kind}/{day}/{uid}.{ext.lstrip('.')}"

    def put_bytes(self, data: bytes, kind: str, ext: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Uploads bytes to Supabase Storage and returns (path, signed_url).
        If disabled, returns (None, None).
        """
        if not self.enabled or not self.client:
            return None, None

        path = self.key_for(kind, ext)
        bucket = self.client.storage.from_(self.bucket)

        # Upload (upsert=True to overwrite on rare collision)
        bucket.upload(file=data, path=path, file_options={"content-type": _mime_for(ext), "upsert": "true"})

        # Create a signed URL
        signed = bucket.create_signed_url(path=path, expires_in=self.expires)
        signed_url = signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl")
        if not signed_url:
            # Some SDK versions return a dict with 'signedURL'; normalize
            signed_url = signed if isinstance(signed, str) else None

        return path, signed_url
