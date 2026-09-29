---
name: resollo-selling
description: Use this skill when the user wants to sell an item on Resollo (resollo.com) or manage what they already sell there - turning phone photos of an item into a Resollo listing, cleaning up product photos before listing, finding out why a listing can't be created, finding draft or inactive listings, and handling incoming offers or orders as a seller. Also use it when the user simply wants to sell something second-hand online and Resollo's MCP tools are connected, even if they don't name Resollo. Works through Resollo's MCP server and, optionally, the free local GIMP, Inkscape and background-removal MCP servers from github.com/resollo/mcp-servers. Not for buying on Resollo (use resollo-buying).
license: MIT
compatibility: Needs Resollo's remote MCP server (https://www.resollo.com/api/mcp) with the seller's personal API key. Photo clean-up and the upload script need local code execution and, optionally, the resollo/mcp-servers photo tools.
metadata:
  author: resollo
  version: "1.0"
---

# Selling on Resollo

Resollo is an international second-hand and new-goods marketplace (8 languages, multi-currency, fixed price and auctions). A seller only supplies photos: Resollo's own AI writes the title, description, category, condition, attributes, semantic profile and a suggested price. Your job is to get good photos in, create the draft, and hand control back to the seller.

## Ground rules

- **Never publish on the seller's behalf.** `products.create` always creates an **inactive** draft. Only the seller activates it, from the `activation_url`. Never tell the user the item is live.
- **Never fill in Resollo's web listing form** with a browser or any other automation. Resollo's AI & Automation Policy forbids third-party AI form-filling; `products.create` is the permitted path.
- **Don't write the listing text yourself.** Leave title, description, category, condition and price to Resollo's AI unless the user explicitly gives you a value to use (`name` ≤100 chars, `description` ≤500 chars, `price`).
- **Protect the API key.** Never print, echo, log or paste it into files or chat. Scripts read it from the `RESOLLO_API_KEY` environment variable.
- **Ask before committing the seller**: accepting, countering or rejecting an offer and rejecting an order all need the user's explicit go-ahead for that specific action.

## Setup (once)

1. The seller creates a personal API key on their Resollo profile page, card "AI Agent Access". One active key per user; generating a new one revokes the old.
2. Add Resollo as a remote MCP server: URL `https://www.resollo.com/api/mcp`, header `Authorization: Bearer <key>`.
3. Optional, for photo clean-up: install the local `bgremoval`, `gimp` and `inkscape` servers from https://github.com/resollo/mcp-servers (each folder's README has the steps).

## Workflow: from photos to a draft listing

### 1. Check the seller can list at all

Call `sellers.status` first, before asking for photos. It returns `can_create_products`, `max_products`, `can_create_auctions`, `has_payment_method`, `has_shipment_method`, `max_images`, `max_price` and `ai_credits_remaining`.

Stop and tell the user exactly what to fix if:

| Field | Problem | What the user does |
|---|---|---|
| `can_create_products` false | plan limit reached | upgrade plan or close a listing on resollo.com |
| `has_payment_method` false | no accepted payment method | add one in their Resollo settings |
| `has_shipment_method` false | no shipment method | add one in their Resollo settings |
| `ai_credits_remaining` < 2 | a draft costs 2 AI credits | buy an AI credit pack or use promo credits |

Also respect `max_images` (and never more than 5) and `max_price`.

### 2. Prepare the photos (recommended)

Good photos sell. If the photo tools are available, run the clean-up in [references/photo-prep.md](references/photo-prep.md): colour/white balance, background removal, tight crop, centred on a 1:1 canvas, exported at 1000×1000. If the tools aren't available, use the originals. JPEG, PNG or WebP, 5 MB max each, 1-5 images of the same item.

### 3. Create the draft

**Don't pass image bytes through your own context.** `products.create` takes base64 image data, and a phone photo is millions of characters of base64. Reading it into the conversation and writing it back out as a tool argument is slow, expensive and easily corrupts the image.

- **With local code execution (preferred):** run [scripts/create_product_upload.py](scripts/create_product_upload.py). It encodes and POSTs the images itself and prints only a small JSON result:
  ```
  RESOLLO_API_KEY=... python3 scripts/create_product_upload.py photo1.jpg photo2.jpg
  ```
  Optional flags: `--price`, `--quantity`, `--business`, `--no-offers`.
- **Without it:** call the MCP tool `products.create` with small, already-compressed images only (the 1000×1000 output of step 2), one call per item.

Limit: 5 `products.create` calls per minute. Each success uses 2 AI credits (autofill + price suggestion).

### 4. Hand over to the seller

Show the seller what came back: `suggested.name`, `suggested.description`, category, condition, `suggested.price` (a range-based suggestion) and the `activation_url`. Tell them clearly:

- the listing is **not visible yet**;
- they should review it and switch it to active at the `activation_url`;
- on first activation it goes through Resollo's moderation before it's public.

If a `product_id` gets lost, `sellers.listings` with `state: "inactive"` finds the draft again.

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

- An error naming a plan, payment or shipment limit means step 1 was skipped or the account changed. Re-run `sellers.status` and report the fix.
- A rate-limit error: wait a minute, don't retry in a loop.
- An image rejected as invalid: Resollo checks the actual decoded bytes, not the declared type. Re-export as JPEG/PNG/WebP.
- For codes and ids (categories, conditions, currencies, payment and shipment methods), call `marketplace.info` instead of guessing.

More: seller guide https://www.resollo.com/en/guides/listing-photos · fees https://www.resollo.com/en/guides/fees-and-payouts · API spec https://resollo.com/openapi/agent-v1.yaml
