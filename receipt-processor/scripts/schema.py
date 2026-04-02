SYSTEM_PROMPT = "You are a receipt data extractor. Extract all available information from the receipt. Use null for any field that cannot be determined."

# JSON Schema for structured outputs.
# - Strict-mode compatible (all fields required, additionalProperties: false).
# - Nullable fields use ["type", "null"] union so the model can express missing data.
RECEIPT_JSON_SCHEMA = {
    "name": "receipt",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "merchant":        {"type": ["string", "null"]},
            "date":            {"type": ["string", "null"], "description": "ISO 8601 date if determinable"},
            "currency":        {"type": ["string", "null"], "description": "3-letter code, e.g. USD"},
            "subtotal":        {"type": ["number", "null"]},
            "tax":             {"type": ["number", "null"]},
            "total":           {"type": ["number", "null"]},
            "payment_method":  {"type": ["string", "null"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity":    {"type": ["number", "null"]},
                        "unit_price":  {"type": ["number", "null"]},
                        "total":       {"type": ["number", "null"]},
                    },
                    "required": ["description", "quantity", "unit_price", "total"],
                    "additionalProperties": False,
                },
            },
            "raw_text": {"type": ["string", "null"]},
        },
        "required": [
            "merchant", "date", "currency", "subtotal", "tax",
            "total", "payment_method", "items", "raw_text",
        ],
        "additionalProperties": False,
    },
}

# Best-effort variant for models that don't support strict mode (e.g. vision model).
RECEIPT_JSON_SCHEMA_BEST_EFFORT = {**RECEIPT_JSON_SCHEMA, "strict": False}
