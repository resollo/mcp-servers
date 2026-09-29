---
name: resollo-buying
description: Use this skill when the user wants to find, evaluate or buy an item on Resollo (resollo.com) - searching listings across countries and currencies, checking a seller's reputation and reviews, asking a seller a question, making or accepting a price offer, placing an order, tracking it, or getting the payment link. Also use it for shopping requests like "find me a used iPhone under 400 euros" when Resollo's MCP tools are connected, even if the user doesn't name Resollo. Every step that commits the user (an offer, an order) needs their explicit approval first; Resollo never processes payment itself. Not for listing items for sale (use resollo-selling).
license: MIT
compatibility: Search and reading work without an account through Resollo's MCP server (https://www.resollo.com/api/mcp). Questions, offers and orders need the buyer's personal API key.
metadata:
  author: resollo
  version: "1.0"
---

# Buying on Resollo

Resollo is an international marketplace for second-hand and new items (8 languages, prices shown in the buyer's currency, fixed price, auctions and Make-an-Offer). You can search, compare and prepare a purchase. **The user makes every commitment.**

## Ground rules

- **Explicit approval before anything binding.** Making an offer, accepting a counter-offer and placing an order all need the user's clear "yes" to that exact item, price, payment and shipment method. An accepted offer turns into an order immediately.
- **`orders.place` needs `confirm: true`.** Set it only after the user has seen the order summary *and* the `payment_safety` text, and approved. Never on your own initiative, never "to save a step".
- **You never pay.** Resollo does not process payments. Buyer and seller settle directly (cash, bank transfer, PayPal, or card via Stripe). For card payment, `orders.checkoutLink` returns a Stripe URL that the user opens and pays themselves.
- **Addresses:** only the user's own saved addresses (`address_key`), or `personal` hand-over. Never type in a free-text address.
- **Public posts:** `questions.ask` posts a public question on the listing. Show the user the exact text and get approval first.
- **Protect the API key.** Never print or repeat it.

## Setup

- Reading (search, details, sellers, reviews, Q&A) works without an account.
- For questions, offers and orders: the user creates a personal API key on their Resollo profile page ("AI Agent Access") and adds Resollo as a remote MCP server: `https://www.resollo.com/api/mcp` with header `Authorization: Bearer <key>`.

## Workflow

### 1. Search

`products.search` with:

- `q`: free text
- `category`: numeric id from `marketplace.info` (don't guess ids)
- `price_min` / `price_max` in the chosen `currency` (ISO code, default USD; use the user's own currency)
- `location`: seller location, e.g. `"HU"` or `"HU:BU"`
- `sort`: `newest`, `price_asc` or `price_desc` (never influenced by paid placement)
- `limit` (max 50) and `cursor` for more pages

Present a short shortlist: name, converted price, condition, seller location, listing type. Say when a listing's native currency differs from the user's.

### 2. Evaluate

- `products.get`: full details, accepted payment and shipment methods, shipping prices, whether offers are enabled, auction end date.
- `sellers.get`: verification badge, member since, completed sales, positive-feedback rating, active listings.
- `reviews.list` and `questions.list`: verified-buyer reviews and existing Q&A for the listing.

Point out risks plainly: a new seller with no feedback, far-away shipping, payment methods with weaker protection (see https://www.resollo.com/en/guides/buying-safely).

### 3. Ask or negotiate (optional)

- `questions.ask`: public question, max 500 characters, after user approval.
- `offers.make`: only on fixed-price listings with offers enabled. Agree the amount with the user first. If the seller accepts, an order is created at that price.
- If the seller counters: show the counter price. Only on the user's approval call `offers.respond` with `action: "accept_counter"`.
- Track with `offers.list` (`role: "buyer"`).

Auctions are bid on in the Resollo web app, not through these tools.

### 4. Place the order

Before calling `orders.place`, show the user one summary:

- item, seller, quantity, price in the listing's own currency (the order is always recorded in that currency) and the approximate amount in the user's currency;
- `payment_method` and `shipment_method` (must be ones the seller accepts);
- delivery address (which saved address) or personal pickup;
- the `payment_safety` guidance for the chosen payment method.

Only after an explicit yes: `orders.place` with `product_id`, `payment_method`, `shipment_method`, optional `address_key`, `quantity`, `comment`, and `confirm: true`. The order starts as **reserved**, and no money moves.

### 5. After ordering

- `orders.status` / `orders.list` (`role: "buyer"`): reserved → dispatched → paid → received.
- Card payment: once the seller has dispatched, `orders.checkoutLink` gives the Stripe payment URL. Hand it to the user; don't open it or pay yourself.
- Confirming receipt and the 14-day withdrawal right are done by the user in the Resollo web app.

## Without the MCP server

For read-only research you can use Resollo's machine-readable files instead:

- platform overview: https://www.resollo.com/llms-full.txt
- all listings per language: https://www.resollo.com/en/products/llms-index.txt
- each listing: `https://www.resollo.com/en/products/<id>/llms.txt`

These can't place orders or offers.
