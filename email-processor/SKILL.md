---
name: email-processor
description: Parse Tesco order confirmation .eml files into an itemized receipt summary using the Anthropic Claude API. Use when processing email receipts, parsing .eml files, extracting grocery order line items, verifying receipt arithmetic, or when the user mentions Tesco email orders or wants to process a forwarded receipt email.
---

# Email Processor

Parses Tesco order confirmation `.eml` files end-to-end using Claude (Anthropic API):

1. **Ingest** — decode the `.eml`, strip HTML → clean plain text
2. **Parse** — Claude extracts structured `Order` / `OrderItem` JSON
3. **QA** — Claude independently verifies the arithmetic
4. **Summary** — prints an itemized receipt to stdout

## Setup

```bash
pip install anthropic
```

API key and model are configured in `email-processor/config.py`:

```python
ANTHROPIC_API_KEY = "sk-ant-..."
TEXT_MODEL = "claude-opus-4-5"
```

## Usage

```bash
# Itemized summary (default)
python email-processor/process_eml.py path/to/order.eml

# Also dump raw parsed JSON after the summary
python email-processor/process_eml.py path/to/order.eml --json

# Skip the QA arithmetic check (faster, one LLM call instead of two)
python email-processor/process_eml.py path/to/order.eml --skip-qa
```

Run from the repo root — the script resolves its own paths automatically.

## Model

| Stage  | Model            | Notes                                      |
|--------|------------------|--------------------------------------------|
| Parse  | `claude-opus-4-5`| JSON extracted from free-form response     |
| QA     | `claude-opus-4-5`| Returns `{"ok", "issues", computed totals}`|

Change `TEXT_MODEL` in `config.py` to switch models for both stages.

## Output Schema

The parsed receipt matches the shared schema in `receipt-processor/scripts/schema.py`. Key fields:

- `merchant` — store name, e.g. `"Tesco"`
- `ordered_at` — ISO 8601 date-time or `null`
- `currency` — 3-letter code, defaults to `"GBP"`
- `subtotal`, `delivery_fee`, `total` — monetary totals
- `basket_discounts[]` — basket-level adjustments; each has `description` and `amount`
- `payment_method` — e.g. `"Pay online"`, `"Clubcard Pay+"`
- `items[]` — one entry per line item:
  - `raw_label` — label exactly as it appears in the email
  - `normalized_label` — cleaned, human-readable product name
  - `quantity`, `unit_price`, `line_total`
  - `item_discount` — positive saving if an offer applies; `null` otherwise

## Mapping to PLAN.md Data Model

| Schema field          | PLAN.md model field      |
|-----------------------|--------------------------|
| `merchant`            | `Order.merchant`         |
| `ordered_at`          | `Order.ordered_at`       |
| `currency`            | `Order.currency`         |
| `subtotal`            | `Order.subtotal`         |
| `delivery_fee`        | `Order.fees`             |
| `basket_discounts`    | `Order.discounts`        |
| `total`               | `Order.total`            |
| `items[].raw_label`   | `OrderItem.raw_label`    |
| `items[].normalized_label` | `OrderItem.normalized_label` |
| `items[].quantity`    | `OrderItem.quantity`     |
| `items[].unit_price`  | `OrderItem.unit_price`   |
| `items[].line_total`  | `OrderItem.line_total`   |

## Error Handling

Errors from the LLM or JSON parsing are printed as `{"error": "..."}` to stdout and the process exits with code 1. Always check the exit code or `error` key before consuming output.

## Workflow

When asked to process a Tesco email receipt:

1. Locate the `.eml` file
2. Run: `python email-processor/process_eml.py path/to/order.eml`
3. Read the itemized summary printed to stdout
4. If `--json` was passed, also parse the structured JSON for persistence
5. Check for `✗ QA check FAILED` warnings and report any arithmetic discrepancies
6. Map output fields to `Order` / `OrderItem` before persisting to the database
