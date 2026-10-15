# Resollo photo upload MCP server

A tiny, local MCP server with one tool, `resollo_upload_photo`, for
[Resollo](https://www.resollo.com)'s **direct upload**: it lets an AI agent upload
listing photos it already created as WebP files (for example with the
[`gimp-mcp`](../gimp-mcp/) server) without a shell and without passing the image
through the conversation.

```
AI app  <--MCP (stdio)-->  resollo_upload_mcp_server/server.py  --HTTPS PUT-->  Resollo signed upload URL
```

## How it fits in

1. Resollo's own connector (`https://www.resollo.com/api/mcp`): `products.create`
   returns `upload_id` and `direct_upload` (`put_urls`, `headers`, `requirements`).
2. Create each photo as a WebP file within `requirements` (at most 1024 px on its
   longest side, metadata stripped, under 5 MB) — e.g. `gimp_export_image` to a
   `.webp` path. Resollo never converts photos.
3. `resollo_upload_photo(path, put_url, headers)` once per photo, with
   `put_urls[i]` (index 0 is the cover) and `direct_upload.headers`.
4. Resollo's connector: `products.createFromUpload` with the `upload_id`.

The [`resollo-selling`](../skills/resollo-selling/) skill walks an agent through it.

## Why it's deliberately narrow

A general "upload this file to that URL" tool would let an agent send any local
file anywhere. This one only:

- reads a `.webp` file with a real WebP signature, up to 5 MB;
- sends it only to a Resollo signed upload URL
  (`https://<project>.supabase.co/storage/v1/object/upload/sign/temp-images/….webp?token=…`);
- forwards only the `apikey` and `x-upsert` headers, with `Content-Type: image/webp`;
- never changes the file.

## Installation

```bash
cd resollo-upload-mcp/resollo_upload_mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

On Windows use `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`.

Then register it with your AI app — see
[`claude_desktop_config.example.json`](claude_desktop_config.example.json)
(replace `/ABSOLUTE/PATH` with where you cloned this repository).

## Tests

```bash
cd resollo-upload-mcp
python3 -m unittest discover -s tests
```

The checks live in `upload_rules.py` and need only the Python standard library.
For development against a local Supabase (`supabase start`), set
`RESOLLO_UPLOAD_ALLOW_LOCAL=1` to also allow `http://127.0.0.1` upload URLs.
