SYSTEM_PROMPT = (
    "You are a Tesco receipt data extractor. "
    "Extract all available information from the plain-text receipt. "
    "Preserve the original item label in raw_label exactly as it appears. "
    "Populate normalized_label with a cleaned, human-readable product name. "
    "Capture item-level discounts separately in item_discount. "
    "Capture basket-wide discounts (e.g. Clubcard savings, promo codes) in basket_discounts. "
    "Set delivery_fee to null if not present. "
    "Currency is GBP unless the receipt states otherwise. "
    "Use null for any field that cannot be determined."
)

# JSON Schema for structured outputs.
# - Strict-mode compatible (all fields required, additionalProperties: false).
# - Nullable fields use ["type", "null"] union so the model can express missing data.
# - Aligns with the Order / OrderItem data model defined in PLAN.md.
RECEIPT_JSON_SCHEMA = {
    "name": "receipt",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "merchant": {
                "type": ["string", "null"],
                "description": "Store or merchant name, e.g. 'Tesco'",
            },
            "ordered_at": {
                "type": ["string", "null"],
                "description": "ISO 8601 date-time when the order was placed, e.g. '2024-03-15T14:30:00'",
            },
            "currency": {
                "type": ["string", "null"],
                "description": "3-letter ISO 4217 code, e.g. 'GBP'",
            },
            "subtotal": {
                "type": ["number", "null"],
                "description": "Sum of item line totals before fees and basket discounts",
            },
            "delivery_fee": {
                "type": ["number", "null"],
                "description": "Delivery or service charge; null if collection or not shown",
            },
            "basket_discounts": {
                "type": "array",
                "description": "Basket-level discounts such as Clubcard savings or promo codes",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "amount": {
                            "type": "number",
                            "description": "Positive value representing the discount magnitude",
                        },
                    },
                    "required": ["description", "amount"],
                    "additionalProperties": False,
                },
            },
            "total": {
                "type": ["number", "null"],
                "description": "Final amount charged to the customer",
            },
            "payment_method": {
                "type": ["string", "null"],
                "description": "e.g. 'Visa', 'Clubcard Pay+', 'PayPal'",
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "raw_label": {
                            "type": "string",
                            "description": "Item label exactly as printed on the receipt",
                        },
                        "normalized_label": {
                            "type": ["string", "null"],
                            "description": "Cleaned, human-readable product name",
                        },
                        "quantity": {"type": ["number", "null"]},
                        "unit_price": {"type": ["number", "null"]},
                        "item_discount": {
                            "type": ["number", "null"],
                            "description": "Item-level discount as a positive value; null if none",
                        },
                        "line_total": {
                            "type": ["number", "null"],
                            "description": "Final price for this line after item-level discount",
                        },
                    },
                    "required": [
                        "raw_label",
                        "normalized_label",
                        "quantity",
                        "unit_price",
                        "item_discount",
                        "line_total",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "merchant",
            "ordered_at",
            "currency",
            "subtotal",
            "delivery_fee",
            "basket_discounts",
            "total",
            "payment_method",
            "items",
        ],
        "additionalProperties": False,
    },
}
