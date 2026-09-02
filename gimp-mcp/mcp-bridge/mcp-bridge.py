#!/usr/bin/env python3
"""
mcp-bridge.py -- GIMP 3 plug-in that opens a local TCP "bridge" so an
external Model Context Protocol (MCP) server can drive a running GIMP
instance.

This file does NOT speak MCP itself. It just exposes a small JSON/TCP
RPC protocol on localhost. The companion `gimp_mcp_server/server.py`
(a separate, ordinary Python process -- no GIMP required) is the actual
MCP server that Claude talks to; it forwards each MCP tool call to this
bridge over the socket and relays the JSON answer back.

    Claude  <--MCP (stdio)-->  gimp_mcp_server/server.py  <--TCP/JSON-->  THIS FILE (inside GIMP)

Install
-------
Copy this whole folder (the one containing this file) into your GIMP
plug-ins directory, keeping the folder name identical to this file's
name (minus the extension) -- that's how GIMP discovers Python plug-ins.

    macOS:   ~/Library/Application Support/GIMP/3.0/plug-ins/mcp-bridge/mcp-bridge.py
    Linux:   ~/.config/GIMP/3.0/plug-ins/mcp-bridge/mcp-bridge.py

Then:
    chmod +x ".../plug-ins/mcp-bridge/mcp-bridge.py"

Restart GIMP. A new menu entry appears at:
    Filters > Development > MCP Bridge > Start Bridge Server
    Filters > Development > MCP Bridge > Stop Bridge Server

Extending it
------------
Add a new function to the OPERATIONS dict at the bottom of this file.
It receives **kwargs (parsed straight from the JSON request's "args")
and must return something JSON-serializable. That's the whole contract
-- no need to touch the socket / menu / plug-in registration code.
See the "CURATED OPERATIONS" section for examples.

For anything you haven't wrapped yet, two escape hatches are always
available from the MCP-server side without editing this file at all:
  - "pdb.call"   -> runs any GIMP PDB procedure by name
  - "python.eval"-> runs an arbitrary Python snippet in this process,
                    with Gimp/GLib/Gio/Gegl already imported
"""

import io
import json
import socket
import struct
import sys
import traceback

import gi  # type: ignore[import-not-found]  # provided only by GIMP's bundled Python

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, GimpUi, Gio, GLib, GObject  # type: ignore[import-not-found]  # noqa: E402

HOST = "127.0.0.1"
PORT = 9877  # change here (and in gimp_mcp_server/server.py) if you need a different port
HEADER_SIZE = 4  # 4-byte big-endian length prefix before every JSON payload


# ---------------------------------------------------------------------------
# Wire protocol helpers
# ---------------------------------------------------------------------------


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed while reading")
        buf += chunk
    return buf


def _recv_message(sock):
    header = _recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack("!I", header)
    payload = _recv_exact(sock, length)
    return json.loads(payload.decode("utf-8"))


def _send_message(sock, obj):
    payload = json.dumps(obj, default=_json_fallback).encode("utf-8")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def _json_fallback(obj):
    """Best-effort serialization for GIMP/GObject values that fall out of
    an operation's return value without an explicit serializer."""
    for getter in ("get_id",):
        if hasattr(obj, getter):
            try:
                return {"__gimp_id__": getattr(obj, getter)(), "__repr__": str(obj)}
            except Exception:
                pass
    return str(obj)


# ---------------------------------------------------------------------------
# Small helpers shared by several operations
# ---------------------------------------------------------------------------


def _get_image(image_id):
    if not Gimp.Image.id_is_valid(image_id):
        raise ValueError(f"No such image id: {image_id!r}")
    image = Gimp.Image.get_by_id(image_id)
    if image is None:
        raise ValueError(f"No such image id: {image_id!r}")
    return image


def _get_layer(layer_id):
    if not Gimp.Item.id_is_valid(layer_id):
        raise ValueError(f"No such layer/item id: {layer_id!r}")
    layer = Gimp.Layer.get_by_id(layer_id)
    if layer is None:
        raise ValueError(f"No such layer id: {layer_id!r}")
    return layer


def _image_summary(image):
    return {
        "id": image.get_id(),
        "name": image.get_name(),
        "width": image.get_width(),
        "height": image.get_height(),
        "type": image.get_base_type().value_name,
        "layers": [layer.get_id() for layer in image.get_layers()],
    }


def _layer_summary(layer):
    ok, x, y = layer.get_offsets()
    return {
        "id": layer.get_id(),
        "name": layer.get_name(),
        "width": layer.get_width(),
        "height": layer.get_height(),
        "opacity": layer.get_opacity(),
        "visible": layer.get_visible(),
        "offset": {"x": x, "y": y} if ok else None,
        "is_text_layer": isinstance(layer, Gimp.TextLayer),
    }


def _color_from_rgba(rgba):
    """rgba: [r, g, b] or [r, g, b, a], each 0-255 or 0.0-1.0."""
    vals = list(rgba)
    if any(v > 1.0 for v in vals[:3]):
        vals = [v / 255.0 for v in vals]
    while len(vals) < 4:
        vals.append(1.0)
    color = Gegl.Color.new("black")
    color.set_rgba(*vals[:4])
    return color


# ---------------------------------------------------------------------------
# CURATED OPERATIONS -- add new ones here; each takes **kwargs, returns JSON
# ---------------------------------------------------------------------------


def op_ping(**_kwargs):
    return {"ok": True, "gimp_version": Gimp.version()}


def op_list_images(**_kwargs):
    return [_image_summary(img) for img in Gimp.get_images()]


def op_get_image(image_id, **_kwargs):
    return _image_summary(_get_image(image_id))


def op_create_image(width, height, name=None, fill_white=True, **_kwargs):
    image = Gimp.Image.new(int(width), int(height), Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(
        image,
        name or "Background",
        int(width),
        int(height),
        Gimp.ImageType.RGB_IMAGE,
        100.0,
        Gimp.LayerMode.NORMAL,
    )
    image.insert_layer(layer, None, 0)
    if fill_white:
        Gimp.context_set_foreground(_color_from_rgba([255, 255, 255]))
        Gimp.Drawable.fill(layer, Gimp.FillType.FOREGROUND)
    # GIMP 3 dropped Gimp.Image.set_name(); an image's display name now
    # follows its associated file (or "[Untitled]"). We already give the
    # background layer the requested name above; mirror it onto the image
    # via a virtual .xcf file path so get_name() reflects it too.
    if name:
        image.set_file(Gio.File.new_for_path(f"{name}.xcf"))
    Gimp.Display.new(image)
    Gimp.displays_flush()
    return _image_summary(image)


def op_open_image(path, **_kwargs):
    file = Gio.File.new_for_path(path)
    image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, file)
    Gimp.Display.new(image)
    Gimp.displays_flush()
    return _image_summary(image)


def op_export_image(image_id, path, **_kwargs):
    """Exports a *copy* of the image to `path`. Format is picked by GIMP
    from the file extension (.png, .jpg, .xcf, .webp, ...).

    Alpha handling: formats that cannot store transparency (.jpg/.jpeg/
    .bmp) get properly flattened onto an opaque background first. Every
    other format (.png, .webp, .xcf, ...) keeps its alpha channel intact --
    layers are merged (not flattened) so a multi-layer image still collapses
    to one, but transparent pixels stay transparent instead of turning
    opaque white. Unconditionally flattening used to silently destroy
    transparency on every PNG export (e.g. a background-removed cutout),
    which only showed up later as an unexpected opaque halo when that PNG
    was composited elsewhere."""
    image = _get_image(image_id)
    dup = image.duplicate()
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in ("jpg", "jpeg", "bmp"):
        dup.flatten()
    elif len(dup.get_layers()) > 1:
        dup.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    file = Gio.File.new_for_path(path)
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, dup, file, None)
    dup.delete()
    return {"exported": path}


def op_delete_image(image_id, **_kwargs):
    image = _get_image(image_id)
    image.delete()
    return {"deleted": image_id}


def op_resize_image(image_id, width, height, **_kwargs):
    image = _get_image(image_id)
    image.scale(int(width), int(height))
    Gimp.displays_flush()
    return _image_summary(image)


def op_crop_image(image_id, width, height, offset_x=0, offset_y=0, **_kwargs):
    image = _get_image(image_id)
    image.crop(int(width), int(height), int(offset_x), int(offset_y))
    Gimp.displays_flush()
    return _image_summary(image)


def op_flatten_image(image_id, **_kwargs):
    image = _get_image(image_id)
    layer = image.flatten()
    Gimp.displays_flush()
    return {"image": _image_summary(image), "layer_id": layer.get_id()}


def op_list_layers(image_id, **_kwargs):
    image = _get_image(image_id)
    return [_layer_summary(layer) for layer in image.get_layers()]


def op_add_layer(image_id, name=None, width=None, height=None, **_kwargs):
    image = _get_image(image_id)
    w = int(width) if width else image.get_width()
    h = int(height) if height else image.get_height()
    layer = Gimp.Layer.new(
        image,
        name or "Layer",
        w,
        h,
        Gimp.ImageType.RGBA_IMAGE,
        100.0,
        Gimp.LayerMode.NORMAL,
    )
    image.insert_layer(layer, None, 0)
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_add_text_layer(
    image_id,
    text,
    x=0,
    y=0,
    font="Sans",
    size=24,
    color=(0, 0, 0),
    **_kwargs,
):
    image = _get_image(image_id)
    # GIMP 3's gimp-text-layer-new wants a Gimp.Font, not a font name string.
    font_obj = Gimp.Font.get_by_name(font) if font else None
    if font_obj is None:
        font_obj = Gimp.context_get_font()
    layer = Gimp.TextLayer.new(image, text, font_obj, float(size), Gimp.Unit.pixel())
    image.insert_layer(layer, None, 0)
    layer.set_offsets(int(x), int(y))
    layer.set_color(_color_from_rgba(list(color)))
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_set_layer_opacity(image_id, layer_id, opacity, **_kwargs):
    _get_image(image_id)
    layer = _get_layer(layer_id)
    layer.set_opacity(float(opacity))
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_set_layer_visibility(image_id, layer_id, visible, **_kwargs):
    _get_image(image_id)
    layer = _get_layer(layer_id)
    layer.set_visible(bool(visible))
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_move_layer(image_id, layer_id, offset_x, offset_y, **_kwargs):
    _get_image(image_id)
    layer = _get_layer(layer_id)
    layer.set_offsets(int(offset_x), int(offset_y))
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_delete_layer(image_id, layer_id, **_kwargs):
    _get_image(image_id)
    layer = _get_layer(layer_id)
    layer.delete()
    Gimp.displays_flush()
    return {"deleted": layer_id}


def op_merge_visible_layers(image_id, **_kwargs):
    image = _get_image(image_id)
    layer = image.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    Gimp.displays_flush()
    return _layer_summary(layer)


def op_select_rectangle(image_id, x, y, width, height, **_kwargs):
    image = _get_image(image_id)
    image.select_rectangle(Gimp.ChannelOps.REPLACE, x, y, width, height)
    Gimp.displays_flush()
    return {"ok": True}


def op_select_none(image_id, **_kwargs):
    image = _get_image(image_id)
    Gimp.Selection.none(image)
    Gimp.displays_flush()
    return {"ok": True}


def op_white_balance(image_id, layer_id=None, **_kwargs):
    """Auto white balance / color-cast correction -- the same effect as
    GIMP's 'Colors > Auto > White Balance' menu entry, done via the
    gimp-drawable-levels-stretch PDB procedure. It stretches each RGB
    channel independently to the full 0-255 range, which evens out a
    yellow/blue/green color cast from bad indoor lighting or a phone's
    auto white balance guessing wrong. Deterministic, no manual input.

    If layer_id is omitted, every layer of the image is corrected (handy
    right after opening a phone photo that's still a single background
    layer). Good as the very first step in a photo-prep pipeline, before
    background removal or anything else."""
    image = _get_image(image_id)
    layers = [_get_layer(layer_id)] if layer_id is not None else list(image.get_layers())
    if not layers:
        raise ValueError(f"Image {image_id!r} has no layers to correct")
    pdb = Gimp.get_pdb()
    proc = pdb.lookup_procedure("gimp-drawable-levels-stretch")
    if proc is None:
        raise RuntimeError(
            "gimp-drawable-levels-stretch PDB procedure not found in this "
            "GIMP version -- try gimp_run_pdb_procedure with a procedure "
            "name from your GIMP's PDB browser instead (Help > Procedure "
            "Browser, search 'stretch' or 'white balance')."
        )
    corrected = []
    for layer in layers:
        config = proc.create_config()
        config.set_property("drawable", layer)
        result = proc.run(config)
        status = result.index(0)
        if status != Gimp.PDBStatusType.SUCCESS:
            raise RuntimeError(
                f"White balance failed on layer {layer.get_id()!r}: {status.value_name}"
            )
        corrected.append(layer.get_id())
    Gimp.displays_flush()
    return {"image": _image_summary(image), "layers_corrected": corrected}


# ---------------------------------------------------------------------------
# ESCAPE HATCHES -- generic PDB call + generic Python eval
# ---------------------------------------------------------------------------


def op_pdb_call(procedure, args=None, **_kwargs):
    """Call any GIMP PDB procedure by name, e.g. 'plug-in-gauss',
    'gimp-image-select-ellipse', 'gimp-curves-spline', ...
    `args` is a plain list of positional arguments in PDB order."""
    pdb = Gimp.get_pdb()
    proc = pdb.lookup_procedure(procedure)
    if proc is None:
        raise ValueError(f"Unknown PDB procedure: {procedure!r}")
    config = proc.create_config()
    arg_names = [spec.name for spec in proc.get_arguments()]
    for name, value in zip(arg_names, args or []):
        try:
            config.set_property(name, value)
        except Exception:
            # last-resort: some argument types need GIMP wrapper objects
            # (e.g. colors, GFile). Surface a clear error instead of
            # silently skipping it.
            raise ValueError(
                f"Could not set argument {name!r} of {procedure!r} to {value!r}. "
                "Try python.eval for full control over the argument's type.",
            )
    result = proc.run(config)
    status = result.index(0)
    if status != Gimp.PDBStatusType.SUCCESS:
        raise RuntimeError(f"{procedure} failed with status {status.value_name}")
    values = []
    for i in range(1, result.length()):
        values.append(_json_fallback(result.index(i)))
    Gimp.displays_flush()
    return {"status": status.value_name, "values": values}


def op_python_eval(code, **_kwargs):
    """Executes an arbitrary Python snippet inside the running GIMP
    process. `Gimp`, `GimpUi`, `GLib`, `GObject`, `Gio`, `Gegl` are
    already imported. Put your answer in a variable called `result`;
    it will be JSON-encoded (best effort) and sent back. Anything
    printed with print(...) is also captured and returned as "stdout".
    """
    scope = {
        "Gimp": Gimp,
        "GimpUi": GimpUi,
        "GLib": GLib,
        "GObject": GObject,
        "Gio": Gio,
        "Gegl": Gegl,
        "result": None,
    }
    stdout = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout
    try:
        exec(code, scope)  # noqa: S102 -- this tool is explicitly meant to run arbitrary code
    finally:
        sys.stdout = old_stdout
    Gimp.displays_flush()
    try:
        json.dumps(scope.get("result"), default=_json_fallback)
        result = scope.get("result")
    except TypeError:
        result = _json_fallback(scope.get("result"))
    return {"result": result, "stdout": stdout.getvalue()}


OPERATIONS = {
    "ping": op_ping,
    "image.list": op_list_images,
    "image.get": op_get_image,
    "image.create": op_create_image,
    "image.open": op_open_image,
    "image.export": op_export_image,
    "image.delete": op_delete_image,
    "image.resize": op_resize_image,
    "image.crop": op_crop_image,
    "image.flatten": op_flatten_image,
    "image.select_rectangle": op_select_rectangle,
    "image.select_none": op_select_none,
    "color.white_balance": op_white_balance,
    "layer.list": op_list_layers,
    "layer.add": op_add_layer,
    "layer.add_text": op_add_text_layer,
    "layer.set_opacity": op_set_layer_opacity,
    "layer.set_visibility": op_set_layer_visibility,
    "layer.move": op_move_layer,
    "layer.delete": op_delete_layer,
    "layer.merge_visible": op_merge_visible_layers,
    "pdb.call": op_pdb_call,
    "python.eval": op_python_eval,
}


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------


class BridgeServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self._stop = False

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen(4)
            srv.settimeout(1.0)
            Gimp.message(f"MCP bridge listening on {self.host}:{self.port}")
            while not self._stop:
                try:
                    client, _addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with client:
                    self._handle_connection(client)
        Gimp.message("MCP bridge stopped.")

    def _handle_connection(self, client):
        client.settimeout(30.0)
        try:
            request = _recv_message(client)
        except Exception as exc:
            try:
                _send_message(client, {"status": "error", "message": str(exc)})
            except Exception:
                pass
            return

        op_name = request.get("op")
        args = request.get("args") or {}

        if op_name == "server.shutdown":
            self._stop = True
            _send_message(client, {"status": "success", "data": {"stopped": True}})
            return

        handler = OPERATIONS.get(op_name)
        if handler is None:
            _send_message(
                client,
                {"status": "error", "message": f"Unknown operation: {op_name!r}"},
            )
            return

        try:
            data = handler(**args)
            _send_message(client, {"status": "success", "data": data})
        except Exception as exc:  # noqa: BLE001 -- report back to the caller, don't crash GIMP
            _send_message(
                client,
                {
                    "status": "error",
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )


# ---------------------------------------------------------------------------
# GIMP plug-in registration
# ---------------------------------------------------------------------------

START_PROC = "plug-in-mcp-bridge-start"
STOP_PROC = "plug-in-mcp-bridge-stop"

_server = None


def _start_bridge(procedure, _config, _data):
    global _server
    _server = BridgeServer()
    try:
        _server.serve_forever()
    except Exception as exc:
        Gimp.message(f"MCP bridge crashed: {exc}")
        return procedure.new_return_values(
            Gimp.PDBStatusType.EXECUTION_ERROR,
            GLib.Error(message=str(exc)),
        )
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def _stop_bridge(procedure, _config, _data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect((HOST, PORT))
            _send_message(sock, {"op": "server.shutdown"})
            _recv_message(sock)
    except Exception as exc:
        Gimp.message(f"Could not reach bridge to stop it (already stopped?): {exc}")
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class MCPBridgePlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return [START_PROC, STOP_PROC]

    def do_set_i18n(self, _procedure_name):
        return False, "", ""

    def do_create_procedure(self, name):
        if name == START_PROC:
            procedure = Gimp.Procedure.new(
                self,
                name,
                Gimp.PDBProcType.PLUGIN,
                _start_bridge,
                None,
            )
            procedure.set_menu_label("Start Bridge Server")
            procedure.set_documentation(
                "Start the MCP bridge server",
                "Opens a localhost TCP socket that an external MCP server "
                "process can use to control this GIMP instance.",
                name,
            )
            procedure.add_menu_path("<Image>/Filters/Development/MCP Bridge")
        else:
            procedure = Gimp.Procedure.new(
                self,
                name,
                Gimp.PDBProcType.PLUGIN,
                _stop_bridge,
                None,
            )
            procedure.set_menu_label("Stop Bridge Server")
            procedure.set_documentation(
                "Stop the MCP bridge server",
                "Signals a running MCP bridge server to shut down.",
                name,
            )
            procedure.add_menu_path("<Image>/Filters/Development/MCP Bridge")

        procedure.add_enum_argument(
            "run-mode",
            "Run mode",
            "The run mode",
            Gimp.RunMode,
            Gimp.RunMode.NONINTERACTIVE,
            GObject.ParamFlags.READWRITE,
        )
        procedure.set_attribution("you", "you", "2026")
        return procedure


Gimp.main(MCPBridgePlugin.__gtype__, sys.argv)
