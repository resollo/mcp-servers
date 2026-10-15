"""
Checks for resollo_upload_photo, kept free of MCP imports so they can be tested
with the standard library alone.

The tool is deliberately narrow: it is NOT a general file uploader (that would
let an agent send any local file anywhere). It only sends a WebP file, only to a
Resollo signed upload URL (Supabase Storage, temp-images bucket), and only with
the headers Resollo asks for. It never converts or changes the file -- the
caller creates it within Resollo's requirements; Resollo validates it.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

MAX_BYTES = 5 * 1024 * 1024
SIGNED_UPLOAD_PATH = "/storage/v1/object/upload/sign/temp-images/"
ALLOWED_HEADERS = {"content-type", "x-upsert", "apikey"}

# Local Supabase (supabase start) for development; off unless explicitly enabled.
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class UploadRejected(ValueError):
    """The request doesn't fit the narrow upload contract; nothing was sent."""


def check_url(put_url: str, allow_local: bool = False) -> None:
    parsed = urlparse(put_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host.endswith(".supabase.co"):
        pass
    elif allow_local and parsed.scheme == "http" and host in LOCAL_HOSTS:
        pass
    else:
        raise UploadRejected("put_url must be a Resollo signed upload URL (https://<project>.supabase.co/...)")
    if not parsed.path.startswith(SIGNED_UPLOAD_PATH) or not parsed.path.endswith(".webp"):
        raise UploadRejected("put_url must be a signed temp-images upload URL for a .webp photo")
    if "token=" not in (parsed.query or ""):
        raise UploadRejected("put_url is missing its signature token")


def read_webp(path: str) -> bytes:
    if not path.lower().endswith(".webp"):
        raise UploadRejected("only .webp files can be uploaded -- create the photo as WebP first")
    real = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(real):
        raise UploadRejected(f"file not found: {path}")
    size = os.path.getsize(real)
    if size == 0 or size > MAX_BYTES:
        raise UploadRejected(f"file must be between 1 byte and {MAX_BYTES} bytes (it is {size})")
    with open(real, "rb") as fh:
        data = fh.read()
    # RIFF....WEBP container signature -- the extension alone proves nothing.
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise UploadRejected("file is not a WebP image (missing RIFF/WEBP signature)")
    return data


def filter_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out = {k: v for k, v in (headers or {}).items() if k.lower() in ALLOWED_HEADERS}
    out = {k: v for k, v in out.items() if k.lower() != "content-type"}
    out["Content-Type"] = "image/webp"
    return out
