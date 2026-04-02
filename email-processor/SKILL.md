---
name: email-processor
description: Parse Tesco order confirmation .eml files into an itemized receipt summary using the Anthropic API. Use when processing email receipts, parsing .eml files, extracting grocery order line items, verifying receipt arithmetic, or when the user mentions Tesco email orders or wants to process a forwarded receipt email.
---

# Email Processor

Extracts an itemized receipt summary from a Tesco order confirmation `.eml` by calling the Anthropic API directly via curl.

## Workflow

1. **Read** the `.eml` file — extract the body text (prefer `text/html` part, fall back to `text/plain`)
2. **Call** the Anthropic API with the email body
3. **Display** the itemized summary from the response

## API Call

API key must be set as `ANTHROPIC_API_KEY` in the environment. Escape the email body as a JSON string and substitute into `<EMAIL_BODY>`:

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-5",
    "max_tokens": 4096,
    "system": "You are a Tesco receipt parser. From the email extract every line item (name, qty, unit price, line total, item discount), all basket-level discounts, subtotal, delivery fee, and total paid. Return a clean plain-text itemized summary.",
    "messages": [{"role": "user", "content": "<EMAIL_BODY>"}]
  }'
```

The response is in `content[0].text` — print it directly as the itemized summary.

## Error Handling

If the response contains `"type": "error"`, read `error.message` and report it. A `credit_balance_too_low` error means the account needs topping up at console.anthropic.com/settings/billing.
