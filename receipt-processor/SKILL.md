---
name: receipt-processor
description: Extract structured JSON data from receipt images or plain text using the Groq LLM API. Use when processing receipts, parsing purchase data, extracting line items or totals, handling store transactions, or when the user mentions receipts, invoices, or expense tracking.
---

# Receipt Processor

Extracts structured receipt data (store, date, items, totals, taxes, payment method) as JSON from an image or text file using Groq's LLM API.

## Setup

```bash
pip install groq
export GROQ_API_KEY="your_key_here"
```

Scripts live in `receipt-processor/scripts/`. Always run from that directory so relative imports resolve.

## Usage

```bash
cd receipt-processor/scripts

# From an image (JPEG, PNG, WEBP, GIF)
python process_receipt.py path/to/receipt.jpg

# From a text file
python process_receipt.py --text path/to/receipt.txt

# Inline text
python process_receipt.py --inline "Store: Walmart\nTotal: $42.50"
```

Output is printed as pretty-printed JSON to stdout.

## Models

| Input | Model | Notes |
|-------|-------|-------|
| Image | `meta-llama/llama-4-scout-17b-16e-instruct` | Best-effort structured output |
| Text  | `openai/gpt-oss-20b` | Strict JSON schema mode |

Configured in `config.py` — change `IMAGE_MODEL` or `TEXT_MODEL` there.

## Output Schema

Key fields returned (see `schema.py` for full schema):

- `store_name`, `store_address`
- `date`, `time`
- `items[]` — `name`, `quantity`, `unit_price`, `total_price`
- `subtotal`, `tax`, `total`
- `payment_method`, `currency`

## Error Handling

Errors are returned as `{"error": "..."}` JSON — never thrown to stderr. Always check for the `error` key before consuming the result.

## Workflow

When asked to process a receipt:

1. Determine input type — image path, text file, or inline string
2. Run the appropriate command above
3. Parse the JSON output
4. Use `error` key to detect failures and report them clearly
