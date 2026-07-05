"""Alibaba Cloud OSS document archive for raw workflow payloads.

Production would receive actual inbound emails/PDFs here; local dev only ever sees
short text, but the archive step is exercised the same way either way. Falls back to
writing under ./local_oss_store/ when OSS isn't configured, so the workflow logic
doesn't need a live Alibaba Cloud account to run.
"""

import os

import oss2

from app.config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_BUCKET_NAME, OSS_ENDPOINT

_LOCAL_STORE_DIR = "local_oss_store"


def _get_bucket() -> oss2.Bucket | None:
    if not (OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET and OSS_ENDPOINT and OSS_BUCKET_NAME):
        return None
    auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)


def store_payload(key: str, content: str) -> str:
    """Archive a raw request payload. Returns an oss:// URI, or a local file path in dev."""
    bucket = _get_bucket()
    if bucket is None:
        os.makedirs(_LOCAL_STORE_DIR, exist_ok=True)
        path = os.path.join(_LOCAL_STORE_DIR, key.replace("/", "_"))
        with open(path, "w") as f:
            f.write(content)
        print(f"[oss:dev-stub] wrote {path}")
        return path

    bucket.put_object(key, content.encode("utf-8"))
    return f"oss://{OSS_BUCKET_NAME}/{key}"
