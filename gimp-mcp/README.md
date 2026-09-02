# GIMP MCP server (custom, extensible)

![version](https://img.shields.io/badge/version-0.1.0-blue)

This is a custom, local MCP server that lets an MCP-compatible AI app directly
drive a running **GIMP 3** instance: open/create/export images, manage layers,
add text to an image, run GIMP filters/effects, and even run arbitrary Python
code inside GIMP.

Install an MCP-compatible AI app — Claude Desktop, Claude Code, Cursor, Windsurf
and others all qualify. It was developed and tested with Claude; the config
examples below use Claude Desktop, but any MCP client works the same way.

## How it works

It consists of two separate pieces:

1. **`mcp-bridge/mcp-bridge.py`** — a GIMP plug-in. This runs *inside GIMP* and
   opens a localhost TCP "bridge" (on port `9877` by default) that accepts simple
   JSON commands.
2. **`gimp_mcp_server/server.py`** — a standalone Python process, independent of
   GIMP. This speaks MCP with your AI app and forwards every tool call to GIMP
   over the bridge.

```
AI app  <--MCP-->  gimp_mcp_server/server.py  <--TCP/JSON-->  mcp-bridge.py (inside GIMP)
```

This split makes it easy to extend: to add a new GIMP operation you write a
short function in `mcp-bridge.py` and register a matching tool in `server.py`.
There are also two "escape hatch" tools that make *anything* reachable without
writing new code:

- `gimp_run_pdb_procedure` — calls any of GIMP's ~1000 built-in PDB procedures
  by name (e.g. `plug-in-gauss` for a Gaussian blur).
- `gimp_run_script` — runs arbitrary Python code inside the GIMP process.

## Installation

The procedure is the same on every platform — only paths and a couple of commands
differ. Each step below has a per-OS variant.

### 1. GIMP plug-in

Copy the `mcp-bridge` folder (together with the `mcp-bridge.py` file inside it)
into GIMP's per-user plug-ins folder, **keeping the folder name unchanged** — the
containing folder and the `.py` file must both be named `mcp-bridge`:

| OS | Path to `mcp-bridge.py` |
| --- | --- |
| macOS | `~/Library/Application Support/GIMP/<version>/plug-ins/mcp-bridge/mcp-bridge.py` |
| Linux | `~/.config/GIMP/<version>/plug-ins/mcp-bridge/mcp-bridge.py` |
| Windows | `%APPDATA%\GIMP\<version>\plug-ins\mcp-bridge\mcp-bridge.py` &nbsp;(i.e. `C:\Users\<you>\AppData\Roaming\GIMP\<version>\plug-ins\...`) |

You can also see (and add) the exact folder from inside GIMP:
**Edit → Preferences → Folders → Plug-ins**.

`<version>` is the installed GIMP major.minor version (e.g. `3.0` or `3.2` —
not necessarily `3.0`, even when talking about "GIMP 3"). If you are unsure, open
GIMP and check `Help > About`, or list the parent folder — it contains exactly
one version-numbered subfolder:

| OS | How to list it |
| --- | --- |
| macOS | `ls ~/Library/Application\ Support/GIMP/` |
| Linux | `ls ~/.config/GIMP/` |
| Windows | open `%APPDATA%\GIMP\` in Explorer, or `dir %APPDATA%\GIMP` in `cmd` |

**macOS / Linux only** — make the plug-in executable (GIMP skips non-executable
`.py` plug-ins on these platforms):

```bash
chmod +x "<plug-ins folder from the table above>/mcp-bridge/mcp-bridge.py"
```

On **Windows** no `chmod` is needed — GIMP runs `.py` plug-ins with its bundled
Python automatically.

Restart GIMP. If all is well, a new menu entry appears:
**Filters → Development → MCP Bridge → Start Bridge Server / Stop Bridge Server**.

> **Important if you modify the plugin code (`mcp-bridge.py`):** GIMP loads the
> plugin only once, at startup. Updating the file on disk is not enough by
> itself — you must **restart GIMP itself** (restarting your MCP client is not
> enough), otherwise the old, in-memory version keeps running and new tool calls
> fail with a vague "Unknown operation" / "Error executing tool" error.

> **Note on GIMP's Python environment:** GIMP 3 ships its own bundled
> Python 3 + PyGObject for plug-ins, which you do not need to install separately.
> If the plug-in does not appear in the menu, check GIMP's error console
> (**Windows → Dockable Dialogs → Error Console**) — it reports if loading the
> file failed.

### 2. The MCP server (client-side process)

This is a normal Python 3 process that runs *outside* GIMP (Python 3.10+
recommended).

**macOS / Linux:**

```bash
cd gimp-mcp/gimp_mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
cd gimp-mcp\gimp_mcp_server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 3. Registering with your MCP client

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
    "gimp": {
      "command": "/absolute/path/to/gimp-mcp/gimp_mcp_server/.venv/bin/python3",
      "args": ["/absolute/path/to/gimp-mcp/gimp_mcp_server/server.py"]
    }
  }
}
```

**Windows** — note the doubled backslashes (this is JSON) and
`Scripts\python.exe` instead of `bin/python3`:

```json
{
  "mcpServers": {
    "gimp": {
      "command": "C:\\absolute\\path\\to\\gimp-mcp\\gimp_mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\absolute\\path\\to\\gimp-mcp\\gimp_mcp_server\\server.py"]
    }
  }
}
```

Restart your MCP client (e.g. Claude Desktop).

## Usage

1. Open GIMP.
2. **Filters → Development → MCP Bridge → Start Bridge Server** — this runs
   blocking while the bridge is alive (this is expected; don't worry if the menu
   entry appears to "spin").
3. Ask your AI app something simple, e.g. "ping GIMP" (`gimp_ping` tool) — if you
   get a response, the connection works.

## Important: I could not test this against a real GIMP

I wrote this server in a cloud container that has no GIMP installed — so the
network/JSON protocol part (the communication between `mcp-bridge.py` and
`server.py`) is tested and works, but I could not actually exercise GIMP 3's own
API calls (the exact signatures of `Gimp.file_save`, `Gimp.Layer.new`, etc.)
bound to a running GIMP. It is fairly likely there will be one or two small
differences against your GIMP version.

If a tool throws an error: the error message (and stack trace) is returned to
the AI app, so just report what happened and we can fix it — or the AI app can
use the `gimp_run_script` tool to inspect the GIMP API live (e.g.
`result = dir(Gimp.Image)` or `result = Gimp.file_save.__doc__`) to figure out
the correct call when a curated tool is off.

## Extending — adding a new capability

Example: let's add a "Gaussian blur" tool.

**Step 1** — in `mcp-bridge/mcp-bridge.py`, add this before the `OPERATIONS` dict:

```python
def op_gaussian_blur(image_id, layer_id, radius=5.0, **_kwargs):
    layer = _get_layer(layer_id)
    pdb = Gimp.get_pdb()
    proc = pdb.lookup_procedure("plug-in-gauss")
    config = proc.create_config()
    config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    config.set_property("image", _get_image(image_id))
    config.set_property("drawable", layer)
    config.set_property("horizontal", radius)
    config.set_property("vertical", radius)
    proc.run(config)
    Gimp.displays_flush()
    return {"ok": True}
```

...and register it in the `OPERATIONS` dict:

```python
OPERATIONS = {
    ...,
    "filter.gaussian_blur": op_gaussian_blur,
}
```

**Step 2** — in `gimp_mcp_server/server.py`, add a tool:

```python
@mcp.tool()
def gimp_gaussian_blur(image_id: int, layer_id: int, radius: float = 5.0) -> dict:
    """Applies a Gaussian blur to a layer."""
    return bridge.call("filter.gaussian_blur", image_id=image_id, layer_id=layer_id, radius=radius)
```

**Step 3** — save the file, then:

> **Critical, easy-to-forget step:** if you *copied* the repo into GIMP's
> plug-ins folder from somewhere else (e.g. a VS Code project folder) during
> installation (see above), then editing `mcp-bridge.py` in the **repo** does
> nothing to the actually loaded, installed copy — GIMP loads from its own
> installed copy at startup, not from the repo. **Copy the updated
> `mcp-bridge.py` over to the installed location again** before you restart
> GIMP. Otherwise the new tool call fails with a vague "Unknown operation" /
> "Error executing tool" error and it looks like the code is broken when in
> fact the old version is still running in memory.

Then restart **GIMP itself** (the plug-in loads only at startup — an MCP client
restart alone is not enough) and your MCP client (because of the MCP server).

That's it — you don't need to touch the socket/protocol code or the menu
registration.

## Available tools (current curated set)

- `gimp_ping`
- `gimp_list_images`, `gimp_get_image`, `gimp_create_image`, `gimp_open_image`,
  `gimp_export_image`, `gimp_delete_image`, `gimp_resize_image`,
  `gimp_crop_image`, `gimp_flatten_image`, `gimp_select_rectangle`,
  `gimp_select_none`
- `gimp_white_balance` (automatic white balance / color correction, via the
  `gimp-drawable-levels-stretch` PDB procedure — deterministic, takes no manual
  input; a good first step on a freshly opened phone photo)
- `gimp_list_layers`, `gimp_add_layer`, `gimp_add_text_layer`,
  `gimp_set_layer_opacity`, `gimp_set_layer_visibility`, `gimp_move_layer`,
  `gimp_delete_layer`, `gimp_merge_visible_layers`
- `gimp_run_pdb_procedure` (any GIMP PDB procedure)
- `gimp_run_script` (arbitrary Python inside GIMP)

## Security note

The `gimp_run_script` tool runs literally arbitrary Python code inside your GIMP
process (with filesystem access too, as far as the GIMP user can reach). That is
the price of the flexibility. Since the bridge only listens on `127.0.0.1`, it is
not reachable from outside (from your local network) — but any program running on
your machine can reach it while the Bridge Server is running. If that worries
you, you can close it any time via the Stop Bridge Server menu entry.

## Credits

The exact GIMP 3 GObject Introspection API calls (e.g. `Gimp.PlugIn`
registration, building a `Gimp.Procedure`) were verified against the source of
the MIT-licensed
[`martinduartemore/mcp-gimp`](https://github.com/martinduartemore/mcp-gimp)
project — with thanks.
