---
name: receipt-processor
description: Extract structured JSON data from plain-text Tesco receipts using the Groq LLM API. Use when processing receipts, parsing purchase data, extracting line items or totals, handling Tesco orders, or when the user mentions receipts, invoices, or expense tracking.
---

# Receipt Processor

Extracts structured receipt data from **plain-text** Tesco receipts (email body, copy-pasted text, or forwarded message) using Groq's LLM API with strict JSON schema mode. Output aligns with the `Order` / `OrderItem` data model defined in `PLAN.md`.

## Setup

```bash
pip install groq
export GROQ_API_KEY="your_key_here"
```

Scripts live in `receipt-processor/scripts/`. Always run from that directory so relative imports resolve.

## Usage

```bash
cd receipt-processor/scripts

# From a text file
python process_receipt.py --text path/to/receipt.txt

# Inline text
python process_receipt.py --inline "Tesco Online\nOrdered: 15 Mar 2024\nMilk x1  £1.10\nTotal: £1.10"
```

Output is printed as pretty-printed JSON to stdout.

## Model

| Input | Model | Notes |
|-------|-------|-------|
| Text  | `openai/gpt-oss-20b` | Strict JSON schema mode |

Configured in `config.py` — change `TEXT_MODEL` there.

## Output Schema

Key fields returned (see `schema.py` for full schema):

- `merchant` — store name, e.g. `"Tesco"`
- `ordered_at` — ISO 8601 date-time, e.g. `"2024-03-15T14:30:00"`
- `currency` — 3-letter code, defaults to `"GBP"`
- `subtotal`, `delivery_fee`, `total` — monetary totals
- `basket_discounts[]` — basket-level savings; each has `description` and `amount`
- `payment_method` — e.g. `"Visa"`, `"Clubcard Pay+"`
- `items[]` — one entry per line item:
  - `raw_label` — label exactly as printed on the receipt
  - `normalized_label` — cleaned, human-readable product name
  - `quantity`, `unit_price`, `line_total`
  - `item_discount` — positive value if an item-level discount applies; `null` otherwise

## Mapping to PLAN.md Data Model

| Schema field | PLAN.md model field |
|---|---|
| `merchant` | `Order.merchant` |
| `ordered_at` | `Order.ordered_at` |
| `currency` | `Order.currency` |
| `subtotal` | `Order.subtotal` |
| `delivery_fee` | `Order.fees` |
| `basket_discounts` | `Order.discounts` |
| `total` | `Order.total` |
| `items[].raw_label` | `OrderItem.raw_label` |
| `items[].normalized_label` | `OrderItem.normalized_label` |
| `items[].quantity` | `OrderItem.quantity` |
| `items[].unit_price` | `OrderItem.unit_price` |
| `items[].line_total` | `OrderItem.line_total` |

## Error Handling

Errors are returned as `{"error": "..."}` JSON — never thrown to stderr. Always check for the `error` key before consuming the result.

## Workflow

When asked to process a receipt:

1. Determine input type — text file path or inline string
2. Run the appropriate command above
3. Parse the JSON output
4. Check `error` key for failures and report them clearly
5. Map the output fields to `Order` / `OrderItem` before persisting
