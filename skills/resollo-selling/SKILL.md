---
name: resollo-selling
description: Use this skill when the user wants to sell an item on Resollo (resollo.com) or manage what they already sell there - turning phone photos of an item into a Resollo listing, cleaning up product photos before listing, finding out why a listing can't be created, finding draft or inactive listings, and handling incoming offers or orders as a seller. Also use it when the user simply wants to sell something second-hand online and Resollo's MCP tools are connected, even if they don't name Resollo. Works through Resollo's MCP server and, optionally, the free local GIMP, Inkscape and background-removal MCP servers from github.com/resollo/mcp-servers. Not for buying on Resollo (use resollo-buying).
license: MIT
compatibility: Needs Resollo's remote MCP server (https://www.resollo.com/api/mcp); the seller signs in through the client's connector sign-in (OAuth) or uses a personal API key. Uploading photos yourself needs a tool that can produce the WebP files (e.g. the free photo MCP servers from github.com/resollo/mcp-servers, ImageMagick or cwebp) and a way to send an HTTP PUT (the resollo-upload MCP server from the same repository, or a shell with curl); otherwise the seller uses Resollo's photo picker. Optional photo clean-up needs the local resollo/mcp-servers photo tools.
metadata:
  author: resollo
  version: "2.1"
---

# Selling on Resollo

Resollo is an international second-hand and new-goods marketplace (8 languages, multi-currency, fixed price and auctions). A seller only supplies photos: Resollo's own AI writes the title, description, category, condition, attributes, semantic profile and a suggested price. `products.create` opens a photo upload that can be completed two ways: the seller picks the photos in **Resollo's photo picker**, or — if you can run commands on the photo files — **you upload them directly**. Your job is to check the account is ready, get the photos in, optionally clean them up first, and hand control back to the seller.

## Ground rules

- **Never publish on the seller's behalf.** `products.create` always creates an **inactive** draft. Only the seller activates it on resollo.com. Never tell the user the item is live.
- **Never put photo bytes into a tool argument** (no base64). Photos go in through the photo picker or a direct upload (step 3). Photos pasted into the conversation can't be forwarded to Resollo; if the user pasted one, explain that and let them pick the file in the photo picker, or ask for the file on disk if you can upload directly.
- **Resollo never converts photos.** For a direct upload you convert them yourself; if you can't, use the photo picker.
- **Never fill in Resollo's web listing form** with a browser or any other automation. Resollo's AI & Automation Policy forbids third-party AI form-filling; `products.create` is the permitted path.
- **Don't write the listing text yourself.** Title, description, category, condition and price all come from Resollo's AI; the seller edits them on resollo.com before activating.
- **Protect the API key**, if the seller uses one. Never print, echo, log or paste it into files or chat.
- **Ask before committing the seller**: accepting, countering or rejecting an offer and rejecting an order all need the user's explicit go-ahead for that specific action.

## Setup (once)

1. Add Resollo as a remote MCP server (connector): `https://www.resollo.com/api/mcp`. Clients with connector sign-in (Claude, ChatGPT and others) ask the seller to sign in, or sign up, the first time a tool needs their account. Nothing else is needed.
2. Only if the client can't sign in to connectors: the seller creates a personal API key on their Resollo profile page, card "AI Agent Access", and the server is added with the header `Authorization: Bearer <key>`. One active key per user; generating a new one revokes the old.
3. Optional, for photo clean-up: install the local `bgremoval`, `gimp` and `inkscape` servers from https://github.com/resollo/mcp-servers (each folder's README has the steps). For uploading the photos yourself without a shell, also the `resollo-upload` server. Listing works without any of them.

## Workflow: from photos to a draft listing

### 1. Check the seller can list at all

Call `sellers.status` first, before opening the photo picker. It returns `can_create_products`, `max_products`, `can_create_auctions`, `has_payment_method`, `has_shipment_method`, `max_images`, `max_price`, `ai_credits_remaining`, `translate_credits_remaining` and the credit purchase links.

Stop and tell the user exactly what to fix if:

| Field | Problem | What the user does |
|---|---|---|
| `can_create_products` false | plan limit reached | upgrade plan or close a listing on resollo.com |
| `has_payment_method` false | no accepted payment method | add one in their Resollo settings |
| `has_shipment_method` false | no shipment method | add one in their Resollo settings |
| `ai_credits_remaining` < 2 | a draft costs 2 AI credits | buy an AI credit pack at `ai_credits_purchase_url` |

### 2. Clean up the photos (optional)

Only if the user wants it and the photo tools are available: run the clean-up in [references/photo-prep.md](references/photo-prep.md) (colour/white balance, background removal, tight crop, centred on a 1:1 canvas). Then either upload the cleaned files directly (step 3, path A), or save them in a folder the user can easily find and tell them where, so they pick those files in the photo picker. Skip this step entirely otherwise; the original phone photos work fine.

### 3. Get the photos in

Call `products.create` (no arguments). It returns `upload_url`, `max_images`, `upload_id` and `direct_upload` (`put_urls`, `headers`, `requirements`, `expires_in_seconds`), and in clients that support MCP Apps it also shows the photo picker. Then take one path:

**A. Direct upload** — when you have a tool that can produce the WebP files from the seller's photos, and a way to send an HTTP PUT:

1. Create each photo (1 to `max_images`, the first one is the cover) as a WebP file within `direct_upload.requirements`: at most 1024 px on its longest side, metadata stripped, under `max_bytes`. A square crop matches how Resollo shows listing photos. Any tool that writes such a file works:
   - **The photo MCP servers in [resollo/mcp-servers](https://github.com/resollo/mcp-servers):** after the clean-up in [references/photo-prep.md](references/photo-prep.md) (or just open + resize in GIMP), `gimp_export_image` to a `.webp` path.
   - **ImageMagick or cwebp** from a shell:
   ```bash
   # ImageMagick (also reads HEIC on most builds); -auto-orient before -strip keeps the photo upright
   magick in.jpg -auto-orient -resize '1024x1024>' -strip -quality 85 0.webp   # ImageMagick 6: convert
   # or libwebp (JPEG/PNG input) -- it ignores EXIF orientation, so prefer ImageMagick for phone photos
   cwebp -q 85 -resize 1024 0 -metadata none in.jpg -o 0.webp
   ```
   On macOS, convert HEIC first if needed: `sips -s format jpeg in.HEIC --out in.jpg`.
2. PUT the raw bytes of photo `i` to `direct_upload.put_urls[i]`, sending every header in `direct_upload.headers`. From a shell:
   ```bash
   curl -fsS -X PUT -H 'Content-Type: image/webp' -H 'x-upsert: true' -H 'apikey: <from headers>' \
     --data-binary @0.webp '<put_urls[0]>'
   ```
   Without a shell, use the [`resollo-upload`](https://github.com/resollo/mcp-servers/tree/main/resollo-upload-mcp) MCP server: `resollo_upload_photo(path, put_url, headers)` once per photo, with `put_urls[i]` and `direct_upload.headers`. It only sends `.webp` files to Resollo upload URLs. Never read the file into the conversation to pass it on.
3. Call `products.createFromUpload` with `upload_id`. It returns `product_id`, the suggested content, the price and its AI range, and `activation_url`.

The URLs expire after `expires_in_seconds` (2 hours); if they did, call `products.create` again. A photo that isn't WebP within the requirements is rejected (`invalid_image`) and never converted: the failed attempt discards the uploaded files, so fix the file, upload all photos again to the same URLs (or open a new upload), and call `products.createFromUpload` again.

**B. Photo picker** — otherwise:

- **Clients that support MCP Apps** (e.g. Claude, ChatGPT) show Resollo's photo picker right in the chat. The seller picks 1 to `max_images` photos (the first is the cover) and presses the upload button. Their browser resizes the photos and strips metadata such as GPS location; HEIC works too.
- **Otherwise** give the seller the returned `upload_url`: a resollo.com page with the same picker (signed in; phone gallery or camera works).

Either way, Resollo's AI then drafts the listing. Each draft uses 2 AI credits (autofill + price suggestion); at most 5 drafts per minute. Opening an upload with `products.create` costs nothing.

### 4. Hand over to the seller

After a direct upload, `products.createFromUpload` already returned the draft. After the in-chat picker, you learn the draft's `product_id`, title and activation link with the user's next message. With the `upload_url` page, wait until the user says they uploaded, then find the draft with `sellers.listings` (`state: "inactive"`). Tell the seller clearly:

- the listing is a **draft and not visible yet**;
- they should review it (title, description, price) and activate it at the activation link;
- on first activation it goes through Resollo's moderation before it's public;
- if `translate_credits_remaining` is above 0: when activating, Resollo can translate the listing into its other languages for 1 translation credit.

## Managing sales

| Task | Tool | Notes |
|---|---|---|
| See own listings in any state | `sellers.listings` | `state`: active, inactive, pending_moderation, rejected, closed |
| See offers received | `offers.list` | `role: "seller"`, optionally `state: "pending"` |
| Answer an offer | `offers.respond` | `action`: accept, reject, counter (needs `counter_price`). **Accept creates a confirmed order immediately.** Get the user's approval first. |
| See orders on own listings | `orders.list` | `role: "seller"` |
| Check one order | `orders.status` | returns reserved / dispatched / paid / received / rejected / closed |
| Reject an order | `orders.reject` | only while the order is still reserved (before payment/dispatch), user approval first |

Done by the seller in the Resollo web app, not by agent tools: marking an order dispatched, answering buyer questions (the app drafts AI replies for them), editing and activating listings.

## If something fails

- An error naming a plan, payment, shipment or credit limit means step 1 was skipped or the account changed. Re-run `sellers.status` and report the fix.
- The picker says the upload expired, or the seller closed it: call `products.create` again for a fresh picker.
- `invalid_image` after a direct upload: a file isn't WebP within `direct_upload.requirements`. Convert it properly and re-upload; Resollo won't convert it for you.
- A rate-limit error: wait a minute, don't retry in a loop.
- For codes and ids (categories, conditions, currencies, payment and shipment methods), call `marketplace.info` instead of guessing.

More: connecting an AI assistant https://www.resollo.com/en/guides/ai-assistant · seller photo guide https://www.resollo.com/en/guides/listing-photos · fees https://www.resollo.com/en/guides/fees-and-payouts · API spec https://resollo.com/openapi/agent-v1.yaml
