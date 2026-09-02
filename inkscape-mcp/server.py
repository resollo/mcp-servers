#!/usr/bin/env python3
"""
Inkscape MCP server.

Unlike GIMP, Inkscape has no built-in way to keep a live, remotely
scriptable window open. An SVG file is just XML though, so this server
takes a simpler and more robust approach:

  - Drawing / editing tools manipulate the SVG file directly as XML
    (via lxml). Inkscape does not need to be installed or running for
    these -- they just read-modify-write the file.
  - Export and Inkscape-specific operations (rasterizing to PNG/PDF,
    text-to-path, path boolean ops, or literally any Inkscape "action")
    shell out to the `inkscape` command-line binary for a single
    invocation, then return.

No persistent process, no socket, no plug-in to install into Inkscape.
Just: `pip install -r requirements.txt`, point Claude Desktop's config
at this file, done.

    Claude  <--MCP (stdio)-->  this file  --(lxml)-->  the .svg file on disk
                                          --(subprocess)-->  `inkscape` CLI

Extending it
------------
Add a new @mcp.tool() function. For pure XML edits, use the `_load`/
`_save` helpers directly. For anything Inkscape's engine has to do
(rendering, boolean ops, autotrace, ...), use `_run_inkscape_actions`
with an Inkscape "action" string -- see `inkscape --action-list` and
https://inkscape.org/develop/documentation/ for the full verb catalog.
`inkscape_run_action` already exposes this generically, so most new
capabilities need zero new code here.
"""

import os
import shutil
import subprocess
from typing import Any

from lxml import etree

try:
    # mcp>=2.0
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    # mcp 1.x
    from mcp.server.fastmcp import FastMCP

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {None: SVG_NS, "xlink": XLINK_NS}
INKSCAPE_BIN = os.environ.get("INKSCAPE_BIN", "inkscape")


def _qn(tag: str) -> str:
    """Qualify a bare SVG tag name, e.g. 'rect' -> '{http://.../svg}rect'."""
    return f"{{{SVG_NS}}}{tag}"


def _check_inkscape() -> None:
    if shutil.which(INKSCAPE_BIN) is None:
        raise RuntimeError(
            f"Could not find the '{INKSCAPE_BIN}' executable on PATH. Install "
            "Inkscape, or set the INKSCAPE_BIN environment variable to its full path.",
        )


def _load(path: str) -> tuple[etree._ElementTree, etree._Element]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No such file: {path}")
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(path, parser)
    return tree, tree.getroot()


def _save(tree: etree._ElementTree, path: str) -> None:
    tree.write(path, xml_declaration=True, encoding="UTF-8", standalone=False)


def _find_by_id(root: etree._Element, element_id: str) -> etree._Element:
    matches = root.xpath("//*[@id=$id]", id=element_id)
    if not matches:
        raise ValueError(f"No element with id={element_id!r} found.")
    return matches[0]


def _existing_ids(root: etree._Element) -> set[str]:
    return set(root.xpath("//@id"))


def _new_id(root: etree._Element, prefix: str) -> str:
    existing = _existing_ids(root)
    n = 1
    while f"{prefix}{n}" in existing:
        n += 1
    return f"{prefix}{n}"


def _apply_style(el: etree._Element, style: dict[str, Any] | None) -> None:
    if not style:
        return
    current = {}
    existing_style = el.get("style")
    if existing_style:
        for decl in existing_style.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                current[k.strip()] = v.strip()
    for k, v in style.items():
        current[k.replace("_", "-")] = str(v)
    el.set("style", ";".join(f"{k}:{v}" for k, v in current.items()))


def _element_summary(el: etree._Element) -> dict[str, Any]:
    tag = etree.QName(el).localname
    attrs = {etree.QName(k).localname if isinstance(k, str) else k: v for k, v in el.attrib.items()}
    return {"id": attrs.get("id"), "tag": tag, "attributes": attrs}


def _run(args: list[str]) -> subprocess.CompletedProcess:
    _check_inkscape()
    result = subprocess.run(  # noqa: S603 -- intentionally shelling out to the inkscape CLI
        [INKSCAPE_BIN, *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"inkscape exited with code {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
    return result


def _run_inkscape_actions(path: str, actions: str) -> str:
    """Runs an Inkscape action string against `path`, saving changes back
    into the same file (as plain SVG). Returns combined stdout+stderr for
    diagnostics."""
    full_actions = f"{actions};export-overwrite;export-plain-svg;export-do"
    result = _run([path, f"--actions={full_actions}"])
    return (result.stdout or "") + (result.stderr or "")


mcp = FastMCP("inkscape")


# ---------------------------------------------------------------------------
# Document tools
# ---------------------------------------------------------------------------


@mcp.tool()
def svg_create(path: str, width: float, height: float, background: str | None = None) -> dict:
    """Create a new blank SVG file at `path` with the given pixel size.
    `background`, if given (e.g. '#ffffff'), adds an opaque background rect."""
    root = etree.Element(_qn("svg"), nsmap=NSMAP)
    root.set("width", str(width))
    root.set("height", str(height))
    root.set("viewBox", f"0 0 {width} {height}")
    root.set("version", "1.1")
    if background:
        bg = etree.SubElement(root, _qn("rect"))
        bg.set("id", "background")
        bg.set("x", "0")
        bg.set("y", "0")
        bg.set("width", str(width))
        bg.set("height", str(height))
        bg.set("fill", background)
    tree = etree.ElementTree(root)
    _save(tree, path)
    return {"path": path, "width": width, "height": height}


@mcp.tool()
def svg_info(path: str) -> dict:
    """Get basic info about an SVG file: size, viewBox, and its top-level element ids."""
    _tree, root = _load(path)
    children = [_element_summary(el) for el in root if isinstance(el.tag, str)]
    return {
        "width": root.get("width"),
        "height": root.get("height"),
        "viewBox": root.get("viewBox"),
        "element_count": len(root.xpath("//*")),
        "top_level_elements": children,
    }


@mcp.tool()
def svg_list_elements(path: str, xpath: str | None = None) -> list:
    """List elements in the SVG, optionally filtered by an XPath expression
    (e.g. \"//*[@fill='#ff0000']\"). Without `xpath`, lists every element
    with an id."""
    _tree, root = _load(path)
    if xpath:
        nsmap = {"svg": SVG_NS}
        matches = root.xpath(xpath, namespaces=nsmap)
    else:
        matches = root.xpath("//*[@id]")
    return [_element_summary(el) for el in matches]


@mcp.tool()
def svg_get_element_xml(path: str, element_id: str) -> str:
    """Return the raw XML of one element, for inspection."""
    _tree, root = _load(path)
    el = _find_by_id(root, element_id)
    return etree.tostring(el, pretty_print=True).decode("utf-8")


# ---------------------------------------------------------------------------
# Shape creation tools
# ---------------------------------------------------------------------------


def _add_shape(
    path: str,
    tag: str,
    attrs: dict[str, Any],
    fill: str | None,
    stroke: str | None,
    stroke_width: float | None,
    element_id: str | None,
    parent_id: str | None,
    id_prefix: str,
) -> dict:
    tree, root = _load(path)
    parent = _find_by_id(root, parent_id) if parent_id else root
    el = etree.SubElement(parent, _qn(tag))
    eid = element_id or _new_id(root, id_prefix)
    el.set("id", eid)
    for k, v in attrs.items():
        if v is not None:
            el.set(k, str(v))
    if fill is not None:
        el.set("fill", fill)
    if stroke is not None:
        el.set("stroke", stroke)
    if stroke_width is not None:
        el.set("stroke-width", str(stroke_width))
    _save(tree, path)
    return _element_summary(el)


@mcp.tool()
def svg_add_rect(
    path: str,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str | None = "#000000",
    stroke: str | None = None,
    stroke_width: float | None = None,
    rx: float | None = None,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a rectangle. `rx` gives rounded corners. Colors are CSS colors
    (e.g. '#ff0000', 'red', 'none')."""
    return _add_shape(
        path,
        "rect",
        {"x": x, "y": y, "width": width, "height": height, "rx": rx},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "rect",
    )


@mcp.tool()
def svg_add_circle(
    path: str,
    cx: float,
    cy: float,
    r: float,
    fill: str | None = "#000000",
    stroke: str | None = None,
    stroke_width: float | None = None,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a circle."""
    return _add_shape(
        path,
        "circle",
        {"cx": cx, "cy": cy, "r": r},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "circle",
    )


@mcp.tool()
def svg_add_ellipse(
    path: str,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    fill: str | None = "#000000",
    stroke: str | None = None,
    stroke_width: float | None = None,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add an ellipse."""
    return _add_shape(
        path,
        "ellipse",
        {"cx": cx, "cy": cy, "rx": rx, "ry": ry},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "ellipse",
    )


@mcp.tool()
def svg_add_line(
    path: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str = "#000000",
    stroke_width: float = 1.0,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a straight line segment."""
    return _add_shape(
        path,
        "line",
        {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        None,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "line",
    )


def _points_attr(points: list[list[float]]) -> str:
    return " ".join(f"{p[0]},{p[1]}" for p in points)


@mcp.tool()
def svg_add_polygon(
    path: str,
    points: list[list[float]],
    fill: str | None = "#000000",
    stroke: str | None = None,
    stroke_width: float | None = None,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a closed polygon. `points` is a list of [x, y] pairs."""
    return _add_shape(
        path,
        "polygon",
        {"points": _points_attr(points)},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "polygon",
    )


@mcp.tool()
def svg_add_polyline(
    path: str,
    points: list[list[float]],
    stroke: str = "#000000",
    stroke_width: float = 1.0,
    fill: str | None = "none",
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add an open polyline (not auto-closed). `points` is a list of [x, y] pairs."""
    return _add_shape(
        path,
        "polyline",
        {"points": _points_attr(points)},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "polyline",
    )


@mcp.tool()
def svg_add_path(
    path: str,
    d: str,
    fill: str | None = "#000000",
    stroke: str | None = None,
    stroke_width: float | None = None,
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a <path> from raw SVG path data (the `d` attribute), e.g.
    'M 10 10 L 90 10 L 50 90 Z'. This is the most flexible shape primitive
    -- anything expressible as an SVG path works here."""
    return _add_shape(
        path,
        "path",
        {"d": d},
        fill,
        stroke,
        stroke_width,
        element_id,
        parent_id,
        "path",
    )


@mcp.tool()
def svg_add_text(
    path: str,
    text: str,
    x: float,
    y: float,
    font_family: str = "sans-serif",
    font_size: float = 16,
    fill: str = "#000000",
    element_id: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Add a text label anchored at (x, y) (baseline, left-aligned)."""
    tree, root = _load(path)
    parent = _find_by_id(root, parent_id) if parent_id else root
    el = etree.SubElement(parent, _qn("text"))
    eid = element_id or _new_id(root, "text")
    el.set("id", eid)
    el.set("x", str(x))
    el.set("y", str(y))
    el.set("font-family", font_family)
    el.set("font-size", str(font_size))
    el.set("fill", fill)
    el.text = text
    _save(tree, path)
    return _element_summary(el)


@mcp.tool()
def svg_add_group(path: str, element_id: str | None = None, parent_id: str | None = None) -> dict:
    """Add an empty <g> group. Pass its id as `parent_id` to later add
    shapes/text directly inside it, or use svg_wrap_in_group to move
    existing elements into a new group."""
    tree, root = _load(path)
    parent = _find_by_id(root, parent_id) if parent_id else root
    el = etree.SubElement(parent, _qn("g"))
    eid = element_id or _new_id(root, "group")
    el.set("id", eid)
    _save(tree, path)
    return _element_summary(el)


# ---------------------------------------------------------------------------
# Editing tools
# ---------------------------------------------------------------------------


@mcp.tool()
def svg_set_attributes(path: str, element_id: str, attributes: dict[str, Any]) -> dict:
    """Set arbitrary XML attributes on an element -- covers fill, stroke,
    transform, opacity, x/y/width/height/d, class, or anything else. Pass
    a value of None for an attribute to remove it."""
    tree, root = _load(path)
    el = _find_by_id(root, element_id)
    for k, v in attributes.items():
        if v is None:
            if k in el.attrib:
                del el.attrib[k]
        else:
            el.set(k, str(v))
    _save(tree, path)
    return _element_summary(el)


@mcp.tool()
def svg_set_style(path: str, element_id: str, style: dict[str, Any]) -> dict:
    """Merge CSS-style properties into an element's `style` attribute, e.g.
    {'fill': '#ff0000', 'opacity': '0.5'}. Existing style properties not
    mentioned are kept."""
    tree, root = _load(path)
    el = _find_by_id(root, element_id)
    _apply_style(el, style)
    _save(tree, path)
    return _element_summary(el)


@mcp.tool()
def svg_remove_element(path: str, element_id: str) -> dict:
    """Delete an element (and its children) from the SVG."""
    tree, root = _load(path)
    el = _find_by_id(root, element_id)
    el.getparent().remove(el)
    _save(tree, path)
    return {"removed": element_id}


@mcp.tool()
def svg_reorder_element(path: str, element_id: str, position: str = "front") -> dict:
    """Change an element's stacking order within its parent. `position` is
    'front', 'back', or an integer index."""
    tree, root = _load(path)
    el = _find_by_id(root, element_id)
    parent = el.getparent()
    parent.remove(el)
    if position == "front":
        parent.append(el)
    elif position == "back":
        parent.insert(0, el)
    else:
        parent.insert(int(position), el)
    _save(tree, path)
    return _element_summary(el)


@mcp.tool()
def svg_wrap_in_group(path: str, element_ids: list[str], group_id: str | None = None) -> dict:
    """Move the given elements (in document order) into a new <g> group,
    inserted where the first element used to be."""
    tree, root = _load(path)
    elements = [_find_by_id(root, eid) for eid in element_ids]
    parent = elements[0].getparent()
    index = list(parent).index(elements[0])
    group = etree.Element(_qn("g"))
    group.set("id", group_id or _new_id(root, "group"))
    for el in elements:
        el.getparent().remove(el)
        group.append(el)
    parent.insert(index, group)
    _save(tree, path)
    return _element_summary(group)


# ---------------------------------------------------------------------------
# Inkscape-CLI-backed tools (need the `inkscape` binary)
# ---------------------------------------------------------------------------


@mcp.tool()
def inkscape_export(
    path: str,
    out_path: str,
    export_format: str | None = None,
    dpi: float = 96,
    element_id: str | None = None,
    area: str = "page",
) -> dict:
    """Export the SVG to PNG/PDF/EPS/PS (or another Inkscape-supported
    format). `export_format` defaults to out_path's extension. `dpi` only
    matters for raster formats. Set `element_id` to export just one
    element (tightly cropped to it). `area` is 'page' or 'drawing'."""
    fmt = export_format or os.path.splitext(out_path)[1].lstrip(".").lower()
    if not fmt:
        raise ValueError("Could not infer export format; pass export_format explicitly.")
    args = [path, f"--export-type={fmt}", f"--export-filename={out_path}", f"--export-dpi={dpi}"]
    if area == "drawing":
        args.append("--export-area-drawing")
    else:
        args.append("--export-area-page")
    if element_id:
        args.append(f"--export-id={element_id}")
        args.append("--export-id-only")
    _run(args)
    if not os.path.exists(out_path):
        raise RuntimeError("inkscape reported success but no output file was produced.")
    return {"exported": out_path, "format": fmt}


@mcp.tool()
def inkscape_object_to_path(path: str, element_ids: list[str]) -> dict:
    """Convert shapes/text to <path> elements (e.g. so they can be freely
    edited as vector paths, or fed into svg_path_boolean). Saves the
    result back into `path`."""
    ids = ",".join(element_ids)
    log = _run_inkscape_actions(path, f"select-by-id:{ids};object-to-path")
    return {"converted": element_ids, "log": log}


@mcp.tool()
def inkscape_path_boolean(path: str, element_ids: list[str], operation: str) -> dict:
    """Combine two or more paths/shapes with a boolean operation:
    'union', 'difference', 'intersection', 'exclusion', 'division', or
    'cut'. The result keeps the id of the first element in `element_ids`.
    Saves the result back into `path`."""
    valid = {"union", "difference", "intersection", "exclusion", "division", "cut"}
    if operation not in valid:
        raise ValueError(f"operation must be one of {sorted(valid)}")
    ids = ",".join(element_ids)
    log = _run_inkscape_actions(path, f"select-by-id:{ids};path-{operation}")
    _tree, root = _load(path)
    result_id = element_ids[0]
    return {
        "operation": operation,
        "result_id": result_id if root.xpath("//*[@id=$id]", id=result_id) else None,
        "log": log,
    }


@mcp.tool()
def inkscape_run_action(path: str, actions: str) -> dict:
    """Run a raw Inkscape action string against the file, saving the result
    back into `path`. This is the generic escape hatch -- any verb from
    `inkscape --action-list` (selection, transforms, path operations,
    filters, text operations, ...) can be chained with ';', e.g.
    'select-by-id:rect1;object-rotate-90-cw'. You do not need to add
    export/save actions yourself; they're appended automatically."""
    log = _run_inkscape_actions(path, actions)
    return {"ran": actions, "log": log}


# ---------------------------------------------------------------------------
# Escape hatch -- arbitrary Python over the parsed SVG tree
# ---------------------------------------------------------------------------


@mcp.tool()
def svg_run_script(path: str, code: str) -> dict:
    """Run an arbitrary Python snippet with the SVG file loaded as an lxml
    tree. Available in scope: `tree` (the ElementTree), `root` (its root
    element), `etree` (lxml.etree), `SVG_NS`, and helpers `qn(tag)` (qualify
    a bare tag name) and `find(id)` (look up an element by id). Assign your
    answer to `result` to get it back; anything printed is returned as
    "stdout". The file is always re-saved after running (even read-only
    scripts -- harmless, just reserializes the same tree), unless you set
    `save = False` in your code.

    Example:
        rects = root.xpath("//*[local-name()='rect']")
        result = [r.get('id') for r in rects]
        save = False
    """
    import io
    import sys as _sys

    tree, root = _load(path)
    scope = {
        "tree": tree,
        "root": root,
        "etree": etree,
        "SVG_NS": SVG_NS,
        "qn": _qn,
        "find": lambda eid: _find_by_id(root, eid),
        "result": None,
        "save": True,
    }
    stdout = io.StringIO()
    old_stdout = _sys.stdout
    _sys.stdout = stdout
    try:
        exec(code, scope)  # noqa: S102 -- this tool is explicitly meant to run arbitrary code
    finally:
        _sys.stdout = old_stdout
    if scope.get("save", True):
        _save(tree, path)
    try:
        import json

        json.dumps(scope.get("result"))
        result = scope.get("result")
    except TypeError:
        result = str(scope.get("result"))
    return {"result": result, "stdout": stdout.getvalue()}


if __name__ == "__main__":
    mcp.run()
