#!/usr/bin/env python3
"""
Background-removal MCP server.

A standalone Python process that speaks MCP over stdio to Claude and runs
local, offline AI background segmentation (rembg / ONNX models) directly in
this process. Unlike the GIMP server, there is no bridge and no GUI app to
talk to -- removing a background is a stateless "bytes in, bytes out" call,
so it all fits in one small file.

Run it directly to sanity-check it starts:
    python3 server.py

Normally it's launched automatically by Claude Desktop / Claude Code via the
"mcpServers" entry in claude_desktop_config.json -- see
../claude_desktop_config.example.json.

First call after startup is slow (loads/downloads the ONNX model, cached
under ~/.u2net/ afterwards); every call after that is fast and fully offline.

Extending it
------------
This intentionally has just one real tool. If you want more control later
(different models, returning a mask instead of a cutout, batch calls), add
another @mcp.tool() function here -- rembg's `remove()` already accepts
`session`, `alpha_matting`, `only_mask`, etc. No bridge/protocol code to add,
since everything runs in this one process.
"""

import os
from pathlib import Path

try:
    # mcp>=2.0
    from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore[import-not-found]
except ImportError:
    # mcp 1.x
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from rembg import new_session, remove

# isnet-general-use: good general-purpose quality/speed balance. Override
# with BGREMOVAL_MODEL if you want to try e.g. "u2net" or "birefnet-general".
DEFAULT_MODEL = os.environ.get("BGREMOVAL_MODEL", "isnet-general-use")

_session = None


def _get_session():
    global _session
    if _session is None:
        # Downloads the model to ~/.u2net/ on first use, then caches it.
        _session = new_session(DEFAULT_MODEL)
    return _session


mcp = FastMCP("bgremoval")


@mcp.tool()
def bgremoval_ping() -> dict:
    """Check whether the background-removal server is up and the AI model is
    loaded (loads/downloads it on first call, so this may be slow once)."""
    _get_session()
    return {"ok": True, "model": DEFAULT_MODEL}


@mcp.tool()
def bgremoval_remove_background(input_path: str, output_path: str) -> dict:
    """Remove the background from a local image file using a local, offline
    AI segmentation model (rembg / ONNX Runtime -- no API key, no network
    calls at inference time once the model is cached). `input_path` must be
    an absolute path readable on this machine (jpg/png/webp/heic/...).
    `output_path` must be an absolute path writable on this machine and
    should end in .png -- the result has an alpha channel (transparent
    background), ready to composite onto something else, e.g. in GIMP."""
    in_path = Path(input_path)
    out_path = Path(output_path)
    if not in_path.is_file():
        raise FileNotFoundError(f"input_path does not exist: {input_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    input_bytes = in_path.read_bytes()
    output_bytes = remove(input_bytes, session=_get_session())
    out_path.write_bytes(output_bytes)

    return {"output_path": str(out_path), "bytes": len(output_bytes)}


if __name__ == "__main__":
    mcp.run()
