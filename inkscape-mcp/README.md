# Inkscape MCP server (custom, extensible)

This is a custom, local MCP server that lets an MCP-compatible AI app directly
create and edit SVG images, and export/convert them with Inkscape.

Install an MCP-compatible AI app — Claude Desktop, Claude Code, Cursor, Windsurf
and others all qualify. It was developed and tested with Claude; the config
examples below use Claude Desktop, but any MCP client works the same way.

## How it works — why it differs from the GIMP one

Unlike the GIMP version, **there is no need for a running, open Inkscape
window**, and there is no plug-in to install. Inkscape has no GIMP-like built-in
"stay open and accept remote commands" mode for a live window — but an SVG is
just plain XML text, so this server consists of a single component:

- The drawing/editing tools modify the SVG file directly, as XML (via the `lxml`
  library). This **does not require Inkscape to be running**.
- For export (PNG/PDF/...) and Inkscape-specific operations (text → path, path
  boolean operations: union, difference, etc.) the server invokes the `inkscape`
  command-line program once and waits for it to finish.

```
AI app  <--MCP-->  server.py  --lxml-->  the .svg file on disk
                              --subprocess-->  the `inkscape` CLI program
```

This is more reliable and simpler to install than a solution that relies on a
live GUI bridge — it does not break if you close Inkscape, and Inkscape does not
even need to be running for most operations.

## Installation

### 1. The MCP server (Python)

**macOS / Linux:**

```bash
cd inkscape-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
cd inkscape-mcp
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. Inkscape itself

Make sure the `inkscape` command is available from a terminal:

```
inkscape --version
```

If it is not on `PATH` (common on macOS with `Inkscape.app`, and on Windows if
you unticked "Add to PATH" in the installer), set the `INKSCAPE_BIN` environment
variable to the full path of the binary. Typical locations:

| OS | Typical `inkscape` binary path |
| --- | --- |
| macOS | `/Applications/Inkscape.app/Contents/MacOS/inkscape` |
| Linux | `/usr/bin/inkscape` (usually already on `PATH`; Flatpak: `flatpak run org.inkscape.Inkscape`) |
| Windows | `C:\Program Files\Inkscape\bin\inkscape.exe` |

You can also point `INKSCAPE_BIN` at the binary from your MCP client's config
(see the `env` block below) instead of changing your system `PATH`.

## Registering with your MCP client

Most MCP clients (Claude Desktop, Cursor, Windsurf, …) use the same `mcpServers`
JSON schema shown below — only the location of the config file differs, so check
your app's docs for that. Add an entry based on `claude_desktop_config.example.json`
(macOS/Linux) or `claude_desktop_config.windows.example.json` (Windows), replacing
the placeholder paths with the **absolute** paths on your machine.

For **Claude Desktop** (Settings → Developer → Edit Config) the file lives at:

| OS | `claude_desktop_config.json` location |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | Claude Desktop is not distributed for Linux; for **Claude Code** use `claude mcp add` or a project `.mcp.json` with the same `command` / `args` |

**macOS / Linux:**

```json
{
  "mcpServers": {
    "inkscape": {
      "command": "/absolute/path/to/inkscape-mcp/.venv/bin/python3",
      "args": ["/absolute/path/to/inkscape-mcp/server.py"],
      "env": {
        "INKSCAPE_BIN": "/Applications/Inkscape.app/Contents/MacOS/inkscape"
      }
    }
  }
}
```

**Windows** — note the doubled backslashes (this is JSON) and
`Scripts\python.exe` instead of `bin/python3`:

```json
{
  "mcpServers": {
    "inkscape": {
      "command": "C:\\absolute\\path\\to\\inkscape-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\absolute\\path\\to\\inkscape-mcp\\server.py"],
      "env": {
        "INKSCAPE_BIN": "C:\\Program Files\\Inkscape\\bin\\inkscape.exe"
      }
    }
  }
}
```

The `env` block is only needed if the `inkscape` command is not on `PATH`. If
you also set up the GIMP server earlier, the two `mcpServers` entries coexist
happily — see the example file.

Restart your MCP client (e.g. Claude Desktop). Try it: "create a 300x200 SVG with
a red rectangle" (`svg_create` + `svg_add_rect`).

## This one is actually tested

Unlike the GIMP version, this server was run end to end against a real, installed
Inkscape 1.2.2 binary (XML editing, PNG/PDF export, text → path conversion, path
union/difference, raw action-string execution, error handling) — all of it
worked. Your Inkscape version (especially if much newer/older) may use different
action names or output formatting in a place or two; if you hit that, let me
know.

## Extending — adding a new capability

There are two ways, depending on whether it is a pure XML modification or needs
the Inkscape engine.

**Pure XML editing** (no Inkscape needed) — e.g. a "draw a star" tool:

```python
@mcp.tool()
def svg_add_star(path: str, cx: float, cy: float, r: float, points: int = 5, fill: str = "#000000") -> dict:
    """Add a regular star polygon."""
    import math
    coords = []
    for i in range(points * 2):
        radius = r if i % 2 == 0 else r * 0.4
        angle = math.pi * i / points - math.pi / 2
        coords.append([cx + radius * math.cos(angle), cy + radius * math.sin(angle)])
    return svg_add_polygon(path, coords, fill=fill)
```

**Built on the Inkscape engine** — e.g. "apply a blur filter":

```python
@mcp.tool()
def inkscape_blur(path: str, element_id: str, amount: float = 2.0) -> dict:
    """Apply a blur filter to an element."""
    log = _run_inkscape_actions(path, f"select-by-id:{element_id};object-blur:{amount}")
    return {"blurred": element_id, "log": log}
```

In both cases you only edit `server.py` and restart your MCP client — there is no
separate "bridge" component to maintain.

## Available tools (current curated set)

- **Document:** `svg_create`, `svg_info`, `svg_list_elements`, `svg_get_element_xml`
- **Shape creation:** `svg_add_rect`, `svg_add_circle`, `svg_add_ellipse`,
  `svg_add_line`, `svg_add_polygon`, `svg_add_polyline`, `svg_add_path`,
  `svg_add_text`, `svg_add_group`
- **Editing:** `svg_set_attributes`, `svg_set_style`, `svg_remove_element`,
  `svg_reorder_element`, `svg_wrap_in_group`
- **Inkscape-based:** `inkscape_export` (PNG/PDF/EPS/...), `inkscape_object_to_path`,
  `inkscape_path_boolean` (union/difference/intersection/...), `inkscape_run_action`
  (any Inkscape "action" — see `inkscape --action-list`)
- **Escape hatch:** `svg_run_script` (arbitrary Python on the `lxml` tree)

## Security note

The `svg_run_script` tool runs arbitrary Python code on your machine, with your
user's privileges (filesystem access included). That is the price of the
flexibility, the same as with GIMP's `gimp_run_script`.
