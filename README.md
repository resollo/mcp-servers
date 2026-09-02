# mcp-servers

Custom, self-hosted [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) servers that let an MCP-compatible AI app — Claude Desktop, Claude Code,
Cursor, Windsurf and others — directly drive real creative tools: automate GIMP
image editing, generate and edit SVG graphics in Inkscape, and remove image
backgrounds with a local, offline AI segmentation model. No cloud APIs, no
vendor lock-in — each server runs entirely on your machine and talks to its
client over stdio/MCP.

Each subfolder is a self-contained server — its own README, version, tests, and
dependencies — and is usable on its own. They were developed and tested with
Claude, but nothing is Claude-specific; each server's README shows how to
register it with a client.

| Server | Version | Description |
| --- | --- | --- |
| [`gimp-mcp`](gimp-mcp/) | 0.1.0 | Drive a running GIMP 3 instance from your AI app — open/export images, manage layers, run filters, run arbitrary PDB procedures or Python inside GIMP. |
| [`inkscape-mcp`](inkscape-mcp/) | 0.1.0 | Create and edit SVG images as XML from your AI app, and export/convert them (PNG/PDF/…), text→path and path boolean ops via the Inkscape CLI. No running Inkscape window needed. |
| [`bgremoval-mcp`](bgremoval-mcp/) | 0.1.0 | Remove an image background from your AI app with a local, offline AI segmentation model (rembg / ONNX Runtime). No API key, no cloud. |

## Built for Resollo

These servers power [Resollo](https://www.resollo.com)'s seller-facing "connect
your AI agent" workflow: a seller runs these three free, local connectors
alongside Resollo's own `agent-api` MCP connector, and their AI agent turns a
rough phone photo into a cleaned-up, correctly-sized listing photo — then
drafts and creates the actual marketplace listing. See
[resollo.com/guides/listing-photos](https://www.resollo.com/guides/listing-photos)
for the full seller-facing walkthrough.

## Versioning

Each server is versioned independently via a `VERSION` file in its folder and a
badge in its README. Bump it on any user-visible change to that server.
