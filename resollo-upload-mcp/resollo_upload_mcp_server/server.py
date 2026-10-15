#!/usr/bin/env python3
"""
Resollo photo upload MCP server.

One narrow tool for Resollo's direct upload: after `products.create` (Resollo's
own MCP connector) returns `direct_upload.put_urls` and `direct_upload.headers`,
an agent that has already created the photos as WebP files (e.g. with the gimp
MCP server) calls `resollo_upload_photo` once per photo, then
`products.createFromUpload` on Resollo's connector.

Why a dedicated tool instead of a shell or gimp_run_script: it can only PUT a
.webp file to a Resollo signed upload URL, so it can't be turned into a general
"send any file anywhere" primitive. It never converts the photo -- Resollo
requires WebP, at most 1024 px, metadata stripped, and rejects anything else.

Run it directly to sanity-check it starts:
    python3 server.py
"""

import os
import urllib.error
import urllib.request

try:
    # mcp>=2.0
    from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore[import-not-found]
except ImportError:
    # mcp 1.x
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from upload_rules import UploadRejected, check_url, filter_headers, read_webp

# Development only: also allow a local Supabase (http://127.0.0.1:54321).
ALLOW_LOCAL = os.environ.get("RESOLLO_UPLOAD_ALLOW_LOCAL") == "1"

mcp = FastMCP("resollo-upload")


@mcp.tool()
def resollo_upload_photo(path: str, put_url: str, headers: dict[str, str] | None = None) -> dict:
    """Upload one listing photo (a local .webp file) to a Resollo signed upload URL.

    Use it for Resollo's direct upload: `path` is a WebP file you already created within
    `direct_upload.requirements` from products.create (at most 1024 px on its longest side,
    metadata stripped, under 5 MB); `put_url` is `direct_upload.put_urls[i]` (index 0 is the
    cover); `headers` is `direct_upload.headers`. Call it once per photo, then call
    products.createFromUpload with the upload_id. The file is sent unchanged -- this tool never
    converts photos, and only accepts .webp files and Resollo signed upload URLs.
    """
    try:
        check_url(put_url, allow_local=ALLOW_LOCAL)
        data = read_webp(path)
        request = urllib.request.Request(put_url, data=data, method="PUT", headers=filter_headers(headers))
        with urllib.request.urlopen(request, timeout=60) as response:
            return {"ok": True, "status": response.status, "bytes": len(data)}
    except UploadRejected as error:
        return {"ok": False, "error": str(error)}
    except urllib.error.HTTPError as error:
        body = error.read(500).decode("utf-8", "replace")
        return {"ok": False, "status": error.code, "error": body or error.reason}
    except urllib.error.URLError as error:
        return {"ok": False, "error": f"upload failed: {error.reason}"}


if __name__ == "__main__":
    mcp.run()
