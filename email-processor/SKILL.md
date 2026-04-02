---
name: email-processor
description: Parse Tesco order confirmation .eml files into an itemized receipt summary using the Anthropic Claude API, and optionally post it to a Telegram group with per-item ownership buttons (Mine / Split / Skip). Use when processing email receipts, parsing .eml files, extracting grocery order line items, verifying receipt arithmetic, sending receipts to Telegram, or when the user mentions Tesco email orders or flatmate expense splitting.
---

# Email Processor

Parses Tesco order confirmation `.eml` files end-to-end using Claude (Anthropic API):

1. **Ingest** — decode the `.eml`, strip HTML → clean plain text
2. **Parse** — Claude extracts structured `Order` / `OrderItem` JSON
3. **QA** — Claude independently verifies the arithmetic
4. **Summary** — prints an itemized receipt to stdout; optionally posts to Telegram

## Setup

```bash
pip install anthropic requests python-telegram-bot
```

Configure in `email-processor/config.py`:

```python
ANTHROPIC_API_KEY  = "sk-ant-..."
TEXT_MODEL         = "claude-opus-4-5"
TELEGRAM_BOT_TOKEN = ""   # from @BotFather
TELEGRAM_CHAT_ID   = ""   # group chat ID (negative integer)
```

## Usage

```bash
# Itemized summary (stdout only)
python email-processor/process_eml.py path/to/order.eml

# Parse + send to Telegram group with inline buttons
python email-processor/process_eml.py path/to/order.eml --telegram

# Also dump raw parsed JSON
python email-processor/process_eml.py path/to/order.eml --json

# Skip QA check (faster, one LLM call)
python email-processor/process_eml.py path/to/order.eml --skip-qa

# Start the bot callback handler (keep running alongside)
python email-processor/bot.py
```

Run all commands from the repo root.

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

## Error Handling

Errors from the LLM or JSON parsing are printed as `{"error": "..."}` to stdout and the process exits with code 1. Always check the exit code or `error` key before consuming output.

## Telegram integration

When `--telegram` is passed, `telegram_sender.py` sends the receipt as HTML to the group with one button row per item:

```
[✅ Mine]  [½ Split 2]  [👥 All share]  [⏭ Skip]
...
[✅ Done — settle up]  [🔄 Reset all]
```

`bot.py` (polling process) handles button taps:
- Updates the keyboard to show who assigned each item (`✅ Mine — @user`)
- On **Done**: computes per-person totals (personal items + even share of shared items, delivery, basket discounts) and posts a settlement reply
- On **Reset**: clears all selections and restores the original keyboard

**Telegram setup checklist:**
- Create bot via @BotFather → set `TELEGRAM_BOT_TOKEN`
- Add bot to the group → get `TELEGRAM_CHAT_ID` (use `/getUpdates` or @userinfobot)
- Bot must be a group member (no admin rights needed)

## Workflow

When asked to process and share a Tesco email receipt:

1. Ensure `bot.py` is running: `python email-processor/bot.py`
2. Run: `python email-processor/process_eml.py path/to/order.eml --telegram`
3. The receipt appears in the group with item ownership buttons
4. Flatmates tap buttons to assign items; tap **Done** to post settlements
5. Check stdout for `✗ QA check FAILED` warnings and report discrepancies
