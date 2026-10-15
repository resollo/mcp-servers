"""Run: python3 -m unittest discover -s tests  (standard library only, no MCP SDK needed)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "resollo_upload_mcp_server"))

from upload_rules import MAX_BYTES, UploadRejected, check_url, filter_headers, read_webp  # noqa: E402

GOOD_URL = (
    "https://abc.supabase.co/storage/v1/object/upload/sign/temp-images/"
    "user/agent-upload/upload/0.webp?token=xyz"
)


def write(name: str, data: bytes) -> str:
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


WEBP = b"RIFF" + (100).to_bytes(4, "little") + b"WEBP" + b"\0" * 100


class CheckUrl(unittest.TestCase):
    def test_accepts_a_resollo_signed_upload_url(self):
        check_url(GOOD_URL)

    def test_rejects_any_other_destination(self):
        for url in [
            "https://evil.example.com/storage/v1/object/upload/sign/temp-images/a/0.webp?token=x",
            "http://abc.supabase.co/storage/v1/object/upload/sign/temp-images/a/0.webp?token=x",
            "https://abc.supabase.co/storage/v1/object/public/product-images/a/0.webp?token=x",
            "https://abc.supabase.co/storage/v1/object/upload/sign/temp-images/a/0.png?token=x",
            "https://abc.supabase.co/storage/v1/object/upload/sign/temp-images/a/0.webp",
            "https://abc.supabase.co.evil.com/storage/v1/object/upload/sign/temp-images/a/0.webp?token=x",
        ]:
            with self.subTest(url=url), self.assertRaises(UploadRejected):
                check_url(url)

    def test_local_supabase_only_when_enabled(self):
        local = "http://127.0.0.1:54321/storage/v1/object/upload/sign/temp-images/a/0.webp?token=x"
        with self.assertRaises(UploadRejected):
            check_url(local)
        check_url(local, allow_local=True)


class ReadWebp(unittest.TestCase):
    def test_reads_a_webp_file(self):
        self.assertEqual(read_webp(write("0.webp", WEBP)), WEBP)

    def test_rejects_non_webp_content_or_extension(self):
        with self.assertRaises(UploadRejected):
            read_webp(write("0.jpg", WEBP))
        with self.assertRaises(UploadRejected):
            read_webp(write("0.webp", b"\xff\xd8\xff\xe0 not really webp"))

    def test_rejects_empty_or_oversized_files(self):
        with self.assertRaises(UploadRejected):
            read_webp(write("0.webp", b""))
        with self.assertRaises(UploadRejected):
            read_webp(write("0.webp", WEBP + b"\0" * MAX_BYTES))


class FilterHeaders(unittest.TestCase):
    def test_keeps_only_the_upload_headers_and_forces_webp(self):
        self.assertEqual(
            filter_headers({"apikey": "k", "x-upsert": "true", "content-type": "text/plain", "Cookie": "s"}),
            {"apikey": "k", "x-upsert": "true", "Content-Type": "image/webp"},
        )


if __name__ == "__main__":
    unittest.main()
