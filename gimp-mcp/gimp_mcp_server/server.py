#!/usr/bin/env python3
"""
GIMP MCP server.

An ordinary Python process (no GObject Introspection / GIMP install
needed on this side) that speaks MCP over stdio to Claude, and forwards
every tool call as a small JSON message over a local TCP socket to the
`mcp-bridge` plug-in running inside a live GIMP 3 instance.

Run it directly to sanity-check it starts:
    python3 server.py

But normally it's launched automatically by Claude Desktop / Claude
Code via the "mcpServers" entry in claude_desktop_config.json -- see
../claude_desktop_config.example.json.

Extending it
------------
1. Add the matching operation to mcp-bridge/mcp-bridge.py's OPERATIONS
   dict (inside GIMP).
2. Add a thin @mcp.tool() wrapper here that calls `bridge.call("your.op", ...)`.
That's it -- no protocol code to touch.

You don't have to do step 1 at all for one-off things: `gimp_run_script`
below already lets Claude run arbitrary Python inside GIMP, and
`gimp_run_pdb_procedure` lets it call any of GIMP's ~1000 built-in PDB
procedures by name.
"""

import json
import os
import socket
import struct
from typing import Any

try:
    # mcp>=2.0
    from mcp.server.mcpserver import MCPServer as FastMCP # type: ignore[import-not-found]
except ImportError:
    # mcp 1.x
    from mcp.server.fastmcp import FastMCP # type: ignore[import-not-found]

HOST = os.environ.get("GIMP_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("GIMP_MCP_PORT", "9877"))
TIMEOUT = float(os.environ.get("GIMP_MCP_TIMEOUT", "30"))
HEADER_SIZE = 4


class BridgeError(RuntimeError):
    pass


class GimpBridgeClient:
    """Talks to the mcp-bridge.py plug-in running inside GIMP.

    Opens a fresh connection per call -- simpler and self-healing if
    GIMP was restarted or the bridge server was stopped/started again.
    """

    def __init__(self, host: str = HOST, port: int = PORT, timeout: float = TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout

    def call(self, op: str, **args: Any) -> Any:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                self._send(sock, {"op": op, "args": args})
                response = self._recv(sock)
        except (ConnectionRefusedError, OSError) as exc:
            raise BridgeError(
                f"Could not reach the GIMP MCP bridge at {self.host}:{self.port}. "
                "Is GIMP running with Filters > Development > MCP Bridge > "
                f"Start Bridge Server active? ({exc})",
            ) from exc

        if response.get("status") != "success":
            raise BridgeError(response.get("message", "Unknown GIMP bridge error"))
        return response.get("data")

    @staticmethod
    def _send(sock: socket.socket, obj: Any) -> None:
        payload = json.dumps(obj).encode("utf-8")
        sock.sendall(struct.pack("!I", len(payload)) + payload)

    @staticmethod
    def _recv(sock: socket.socket) -> Any:
        header = GimpBridgeClient._recv_exact(sock, HEADER_SIZE)
        (length,) = struct.unpack("!I", header)
        payload = GimpBridgeClient._recv_exact(sock, length)
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connection closed while reading")
            buf += chunk
        return buf


bridge = GimpBridgeClient()
mcp = FastMCP("gimp")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@mcp.tool()
def gimp_ping() -> dict:
    """Check whether GIMP and the bridge plug-in are reachable."""
    return bridge.call("ping")


# ---------------------------------------------------------------------------
# Image tools
# ---------------------------------------------------------------------------


@mcp.tool()
def gimp_list_images() -> list:
    """List every image currently open in GIMP (id, name, size, layers)."""
    return bridge.call("image.list")


@mcp.tool()
def gimp_get_image(image_id: int) -> dict:
    """Get details of one open image by its id."""
    return bridge.call("image.get", image_id=image_id)


@mcp.tool()
def gimp_create_image(width: int, height: int, name: str | None = None) -> dict:
    """Create a new blank (white) RGB image and open it in GIMP."""
    return bridge.call("image.create", width=width, height=height, name=name)


@mcp.tool()
def gimp_open_image(path: str) -> dict:
    """Open an image file (png/jpg/xcf/...) from disk into GIMP. `path` must
    be an absolute path readable by the machine running GIMP."""
    return bridge.call("image.open", path=path)


@mcp.tool()
def gimp_export_image(image_id: int, path: str) -> dict:
    """Export a flattened copy of an image to disk. The output format is
    picked from the file extension in `path` (.png, .jpg, .webp, .xcf, ...).
    `path` must be an absolute path writable by the machine running GIMP."""
    return bridge.call("image.export", image_id=image_id, path=path)


@mcp.tool()
def gimp_delete_image(image_id: int) -> dict:
    """Close/delete an image from GIMP's memory (does not touch any file on disk)."""
    return bridge.call("image.delete", image_id=image_id)


@mcp.tool()
def gimp_resize_image(image_id: int, width: int, height: int) -> dict:
    """Scale the whole image (and all its layers) to a new pixel size."""
    return bridge.call("image.resize", image_id=image_id, width=width, height=height)


@mcp.tool()
def gimp_crop_image(
    image_id: int,
    width: int,
    height: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> dict:
    """Crop the image canvas to width x height, anchored at (offset_x, offset_y)."""
    return bridge.call(
        "image.crop",
        image_id=image_id,
        width=width,
        height=height,
        offset_x=offset_x,
        offset_y=offset_y,
    )


@mcp.tool()
def gimp_flatten_image(image_id: int) -> dict:
    """Flatten all layers of an image into a single background layer."""
    return bridge.call("image.flatten", image_id=image_id)


@mcp.tool()
def gimp_select_rectangle(image_id: int, x: int, y: int, width: int, height: int) -> dict:
    """Set a rectangular selection on the image (replaces any existing selection)."""
    return bridge.call(
        "image.select_rectangle",
        image_id=image_id,
        x=x,
        y=y,
        width=width,
        height=height,
    )


@mcp.tool()
def gimp_select_none(image_id: int) -> dict:
    """Clear the current selection on the image."""
    return bridge.call("image.select_none", image_id=image_id)


@mcp.tool()
def gimp_white_balance(image_id: int, layer_id: int | None = None) -> dict:
    """Auto white-balance / color-cast correction -- equivalent to GIMP's
    'Colors > Auto > White Balance', via gimp-drawable-levels-stretch.
    Stretches each RGB channel independently so a yellow/blue color cast
    from bad indoor lighting evens out. Deterministic (no manual input,
    no iteration needed). If layer_id is omitted, every layer in the
    image is corrected. Use this as the first step on a freshly opened
    phone photo, before background removal or anything else."""
    return bridge.call("color.white_balance", image_id=image_id, layer_id=layer_id)


# ---------------------------------------------------------------------------
# Layer tools
# ---------------------------------------------------------------------------


@mcp.tool()
def gimp_list_layers(image_id: int) -> list:
    """List every layer of an image (id, name, size, opacity, visibility)."""
    return bridge.call("layer.list", image_id=image_id)


@mcp.tool()
def gimp_add_layer(
    image_id: int,
    name: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    """Add a new empty transparent layer to an image (defaults to full image size)."""
    return bridge.call("layer.add", image_id=image_id, name=name, width=width, height=height)


@mcp.tool()
def gimp_add_text_layer(
    image_id: int,
    text: str,
    x: int = 0,
    y: int = 0,
    font: str = "Sans",
    size: int = 24,
    color: list[int] = [0, 0, 0],  # noqa: B006 -- read-only default, fine here
) -> dict:
    """Add a text layer. `color` is [r, g, b] with each value 0-255."""
    return bridge.call(
        "layer.add_text",
        image_id=image_id,
        text=text,
        x=x,
        y=y,
        font=font,
        size=size,
        color=color,
    )


@mcp.tool()
def gimp_set_layer_opacity(image_id: int, layer_id: int, opacity: float) -> dict:
    """Set a layer's opacity (0-100)."""
    return bridge.call(
        "layer.set_opacity",
        image_id=image_id,
        layer_id=layer_id,
        opacity=opacity,
    )


@mcp.tool()
def gimp_set_layer_visibility(image_id: int, layer_id: int, visible: bool) -> dict:
    """Show or hide a layer."""
    return bridge.call(
        "layer.set_visibility",
        image_id=image_id,
        layer_id=layer_id,
        visible=visible,
    )


@mcp.tool()
def gimp_move_layer(image_id: int, layer_id: int, offset_x: int, offset_y: int) -> dict:
    """Move a layer to an absolute (offset_x, offset_y) position on the canvas."""
    return bridge.call(
        "layer.move",
        image_id=image_id,
        layer_id=layer_id,
        offset_x=offset_x,
        offset_y=offset_y,
    )


@mcp.tool()
def gimp_delete_layer(image_id: int, layer_id: int) -> dict:
    """Delete a layer from an image."""
    return bridge.call("layer.delete", image_id=image_id, layer_id=layer_id)


@mcp.tool()
def gimp_merge_visible_layers(image_id: int) -> dict:
    """Merge all currently visible layers of an image into one."""
    return bridge.call("layer.merge_visible", image_id=image_id)


# ---------------------------------------------------------------------------
# Escape hatches -- this is what makes the server open-ended/extensible
# ---------------------------------------------------------------------------


@mcp.tool()
def gimp_run_pdb_procedure(procedure: str, args: list | None = None) -> dict:
    """Call any GIMP PDB (procedure database) procedure by its registered
    name, e.g. 'plug-in-gauss' (Gaussian blur), 'gimp-curves-spline',
    'gimp-image-convert-grayscale', 'gimp-levels-stretch'. `args` is a
    plain list of positional arguments in the order the PDB procedure
    expects them (use gimp_run_script with pdb lookups to inspect a
    procedure's argument list if unsure)."""
    return bridge.call("pdb.call", procedure=procedure, args=args or [])


@mcp.tool()
def gimp_run_script(code: str) -> dict:
    """Run an arbitrary Python snippet inside the live GIMP process. Use
    this for anything the other tools don't cover. Gimp, GimpUi, GLib,
    GObject, Gio and Gegl are already imported. Assign your answer to a
    variable named `result` to get it back; anything printed with
    print(...) is returned as "stdout". Example:
        images = Gimp.get_images()
        result = [(img.get_id(), img.get_name()) for img in images]
    """
    return bridge.call("python.eval", code=code)


if __name__ == "__main__":
    mcp.run()
