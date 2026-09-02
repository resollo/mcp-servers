# Background-removal MCP server (custom, extensible)

![version](https://img.shields.io/badge/version-0.1.0-blue)

This is a custom, local MCP server that lets an MCP-compatible AI app remove the
background from an image using a local, offline AI segmentation model (**rembg**,
ONNX Runtime) — no API key, no cloud, and after the first call (when the model is
downloaded) no network access is needed either.

Install an MCP-compatible AI app — Claude Desktop, Claude Code, Cursor, Windsurf
and others all qualify. It was developed and tested with Claude; the config
examples below use Claude Desktop, but any MCP client works the same way.

## How it works

Unlike the GIMP server, there is **no bridge** here: background removal is a plain
"bytes in, bytes out" function call. There is no running GUI application to talk
to — everything runs inside a single Python process:

```
AI app  <--MCP (stdio)-->  bgremoval_mcp_server/server.py  (rembg in-process)
```

This is also simpler than the GIMP integration: nothing to copy into a plug-ins
folder, no application restart, no localhost TCP port.

## Why a separate server, and not inside GIMP?

We tried it: GIMP's classic color/hue-based selection tools cannot do reliable
background cutouts (they see "color", not an "object") — that needs real AI
segmentation. We also tried a Node.js solution
(`@imgly/background-removal-node`), but its native dependency (`sharp`) only runs
in a real macOS Node install, not in an isolated Linux VM. rembg (Python, ONNX
Runtime) ships prebuilt binary wheels for macOS ARM, so it does not have that
problem.

## Installation

The steps are the same on every platform — only paths and a couple of commands
differ.

**macOS / Linux:**

```bash
cd bgremoval-mcp/bgremoval_mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
cd bgremoval-mcp\bgremoval_mcp_server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

This installs `rembg` and the `mcp` Python SDK. The AI model itself
(~40–170 MB, depending on the chosen model) is downloaded only on the **first
tool call**, into a per-user cache — from then on it works offline:

| OS | Model cache location |
| --- | --- |
| macOS / Linux | `~/.u2net/` |
| Windows | `%USERPROFILE%\.u2net\` |

## Registering with your MCP client

Most MCP clients (Claude Desktop, Cursor, Windsurf, …) use the same `mcpServers`
JSON schema shown below — only the location of the config file differs, so check
your app's docs for that. Add an entry based on `claude_desktop_config.example.json`
(macOS/Linux) or `claude_desktop_config.windows.example.json` (Windows), replacing
the placeholder paths with the **absolute** paths on your machine. Put it
alongside any `gimp` / `inkscape` entries you already have.

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
    "gimp": { "...": "..." },
    "inkscape": { "...": "..." },
    "bgremoval": {
      "command": "/absolute/path/to/bgremoval-mcp/bgremoval_mcp_server/.venv/bin/python3",
      "args": ["/absolute/path/to/bgremoval-mcp/bgremoval_mcp_server/server.py"]
    }
  }
}
```

**Windows** — note the doubled backslashes (this is JSON) and
`Scripts\python.exe` instead of `bin/python3`:

```json
{
  "mcpServers": {
    "bgremoval": {
      "command": "C:\\absolute\\path\\to\\bgremoval-mcp\\bgremoval_mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\absolute\\path\\to\\bgremoval-mcp\\bgremoval_mcp_server\\server.py"]
    }
  }
}
```

Restart your MCP client (e.g. Claude Desktop).

## Usage

Ask your AI app to "ping the bgremoval server" (`bgremoval_ping` tool) — the first
call can be slow (model download), after that it is fast. Then: "cut out the
background from photo X" → `bgremoval_remove_background(input_path, output_path)`
— the result is a transparent-background PNG, which e.g. GIMP can then composite
onto a clean background.

## Available tools

- `bgremoval_ping`
- `bgremoval_remove_background(input_path, output_path)`

## Extending — adding a new capability

Since there is no bridge/protocol layer, a new capability (e.g. returning just
the mask instead of a cutout, or picking a different model per call) is simply a
new `@mcp.tool()` function in `server.py` that passes the other `rembg.remove()`
parameters (`session`, `alpha_matting`, `only_mask`, ...). There is no second
file to edit, and no GIMP restart.

## Security note

This server only does what its two tools allow (ping, background removal on a
given input/output file path) — there is no `run_script`-style "escape hatch"
that would run arbitrary code, because there is no underlying application (like
GIMP) here that would be worth driving with an arbitrary script.
