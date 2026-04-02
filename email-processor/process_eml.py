#!/usr/bin/env python3
"""
Agentic Tesco receipt processor for .eml files.

Pipeline:
  1. Ingest  – parse the .eml, decode quoted-printable HTML, strip to clean text
  2. Parse   – LLM extracts structured Order / OrderItem data (strict JSON schema)
  3. QA      – LLM independently verifies the arithmetic; flags mismatches
  4. Summary – print itemized receipt to stdout
"""

import argparse
import email as email_lib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Reuse schema from the receipt-processor sibling package
sys.path.insert(0, str(Path(__file__).parent.parent / "receipt-processor" / "scripts"))
# Local config takes precedence
sys.path.insert(0, str(Path(__file__).parent))

try:
    import anthropic
except ImportError:
    print("anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)

from config import ANTHROPIC_API_KEY, TEXT_MODEL
from schema import RECEIPT_JSON_SCHEMA, SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Stage 1: Ingest – .eml → clean plain text
# ---------------------------------------------------------------------------

class _HtmlTextExtractor(HTMLParser):
    """Convert HTML to readable plain text via stdlib html.parser."""

    _BLOCK_TAGS = {"tr", "br", "p", "h1", "h2", "h3", "h4", "li", "div", "td"}
    _SKIP_TAGS = {"script", "style", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            chunk = data.strip()
            if chunk:
                self._parts.append(chunk + " ")

    def get_text(self) -> str:
        lines = []
        for line in "".join(self._parts).splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines)


def ingest_eml(eml_path: str) -> str:
    """
    Stage 1 – Ingest.
    Parse .eml, decode quoted-printable, return clean plain text.
    Prefers text/html part; falls back to text/plain.
    """
    raw = Path(eml_path).read_bytes()
    msg = email_lib.message_from_bytes(raw)

    html_body: str | None = None
    text_body: str | None = None

    for part in msg.walk():
        ct = part.get_content_type()
        payload_bytes = part.get_payload(decode=True)
        if payload_bytes is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload_bytes.decode(charset, errors="replace")
        if ct == "text/html" and html_body is None:
            html_body = decoded
        elif ct == "text/plain" and text_body is None:
            text_body = decoded

    if html_body:
        extractor = _HtmlTextExtractor()
        extractor.feed(html_body)
        return extractor.get_text()

    if text_body:
        return text_body

    # last-resort: treat entire payload as text
    fallback = msg.get_payload(decode=True)
    return fallback.decode("utf-8", errors="replace") if isinstance(fallback, bytes) else str(fallback)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response (handles markdown fences)."""
    if not text or not text.strip():
        raise ValueError("LLM returned an empty response")
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError(f"No JSON object found in response: {text[:200]!r}")


# ---------------------------------------------------------------------------
# Stage 2: Parse – plain text → structured receipt dict
# ---------------------------------------------------------------------------

def parse_receipt(client: anthropic.Anthropic, text: str) -> dict:
    """
    Stage 2 – Parse.
    Call the LLM with the strict receipt JSON schema and return the parsed dict.
    """
    schema_hint = (
        "Respond with ONLY a valid JSON object that matches this schema:\n"
        + json.dumps(RECEIPT_JSON_SCHEMA, indent=2)
    )
    response = client.messages.create(
        model=TEXT_MODEL,
        max_tokens=4096,
        temperature=0,
        system=f"{SYSTEM_PROMPT}\n\n{schema_hint}",
        messages=[{"role": "user", "content": text}],
    )
    return _extract_json(response.content[0].text)


# ---------------------------------------------------------------------------
# Stage 3: QA – verify arithmetic independently
# ---------------------------------------------------------------------------

QA_SYSTEM_PROMPT = (
    "You are a receipt QA checker. "
    "Given a structured receipt JSON, verify that the arithmetic is correct:\n"
    "  - sum of all item line_totals should equal subtotal\n"
    "  - subtotal minus sum of basket_discount amounts plus delivery_fee should equal total\n"
    "  - rounding to 2 decimal places (GBP)\n"
    "You MUST reply with ONLY a raw JSON object and absolutely nothing else — "
    "no prose, no markdown, no code fences. Example:\n"
    '{"ok": true, "issues": [], "computed_items_sum": 89.25, "computed_total": 89.19}'
)


def qa_check(client: anthropic.Anthropic, receipt: dict) -> dict:
    """
    Stage 3 – QA.
    Ask the LLM to independently verify the receipt totals.
    Returns {"ok": bool, "issues": [...], "computed_items_sum": n, "computed_total": n}
    """
    response = client.messages.create(
        model=TEXT_MODEL,
        max_tokens=512,
        temperature=0,
        system=QA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(receipt)}],
    )
    return _extract_json(response.content[0].text)


# ---------------------------------------------------------------------------
# Stage 4: Summary – pretty-print itemized receipt
# ---------------------------------------------------------------------------

def _sym(receipt: dict) -> str:
    return "£" if (receipt.get("currency") or "GBP") == "GBP" else (receipt.get("currency", "") + " ")


def print_summary(receipt: dict, qa: dict) -> None:
    sym = _sym(receipt)

    def money(v) -> str:
        return f"{sym}{v:.2f}" if v is not None else "N/A"

    print()
    print("=" * 68)
    print("  TESCO ORDER — ITEMIZED SUMMARY")
    print("=" * 68)
    print(f"  Merchant   : {receipt.get('merchant') or 'Tesco'}")
    print(f"  Date       : {receipt.get('ordered_at') or 'N/A'}")
    print(f"  Currency   : {receipt.get('currency') or 'GBP'}")
    print(f"  Payment    : {receipt.get('payment_method') or 'N/A'}")
    print()

    # ── Line items ──────────────────────────────────────────────────────────
    items = receipt.get("items") or []
    col_label = 42
    print(f"  {'QTY':<5} {'ITEM':<{col_label}} {'UNIT':>7}  {'TOTAL':>8}  {'SAVED':>8}")
    print("  " + "─" * 74)
    for item in items:
        label = (item.get("normalized_label") or item.get("raw_label") or "?")[:col_label]
        qty   = item.get("quantity")
        qty_s = f"{qty:g}" if qty is not None else "?"
        unit  = item.get("unit_price")
        tot   = item.get("line_total")
        disc  = item.get("item_discount")
        disc_s = f"-{sym}{disc:.2f}" if disc else ""
        print(f"  {qty_s:<5} {label:<{col_label}} {money(unit):>7}  {money(tot):>8}  {disc_s:>8}")
    print("  " + "─" * 74)

    # ── Basket discounts ─────────────────────────────────────────────────────
    basket_discounts = receipt.get("basket_discounts") or []
    if basket_discounts:
        print()
        print("  Basket discounts / adjustments:")
        for bd in basket_discounts:
            amt = bd["amount"]
            # positive amount = saving (show as negative), negative = charge-waiver (show as positive)
            sign = "-" if amt >= 0 else "+"
            print(f"    - {bd['description']:<40} {sign}{sym}{abs(amt):.2f}")

    # ── Totals ───────────────────────────────────────────────────────────────
    print()
    subtotal     = receipt.get("subtotal")
    delivery_fee = receipt.get("delivery_fee")
    total        = receipt.get("total")

    item_savings = sum((item.get("item_discount") or 0) for item in items)
    basket_savings = sum((bd.get("amount") or 0) for bd in basket_discounts)
    total_savings = item_savings + basket_savings

    if subtotal is not None:
        print(f"  {'Basket before offers':<35} {money(subtotal):>10}")
    if total_savings:
        print(f"  {'Total savings':<35} {'-' + money(total_savings):>10}")
    if delivery_fee is not None:
        label = "Delivery fee"
        print(f"  {label:<35} {money(delivery_fee):>10}")
    if total is not None:
        print()
        print(f"  {'TOTAL PAID':<35} {money(total):>10}")

    # ── QA result ────────────────────────────────────────────────────────────
    print()
    if qa.get("ok"):
        print("  ✓ QA check passed — arithmetic verified")
    else:
        print("  ✗ QA check FAILED:")
        for issue in qa.get("issues") or []:
            print(f"      • {issue}")
        c_items = qa.get("computed_items_sum")
        c_total = qa.get("computed_total")
        if c_items is not None:
            print(f"    Computed items sum : {money(c_items)}")
        if c_total is not None:
            print(f"    Computed total     : {money(c_total)}")

    print("=" * 68)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agentic Tesco .eml receipt parser — extract, parse, QA, summarise."
    )
    parser.add_argument("eml", help="Path to the .eml receipt file")
    parser.add_argument(
        "--json", action="store_true",
        help="Dump raw parsed JSON after the summary"
    )
    parser.add_argument(
        "--skip-qa", action="store_true",
        help="Skip the QA verification LLM call"
    )
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Stage 1
    print("[1/3] Ingesting EML …", file=sys.stderr)
    text = ingest_eml(args.eml)

    # Stage 2
    print("[2/3] Parsing receipt with LLM …", file=sys.stderr)
    try:
        receipt = parse_receipt(client, text)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        sys.exit(1)

    # Stage 3
    if args.skip_qa:
        qa_result = {"ok": True, "issues": [], "computed_items_sum": None, "computed_total": None}
    else:
        print("[3/3] Running QA check …", file=sys.stderr)
        try:
            qa_result = qa_check(client, receipt)
        except Exception as exc:
            qa_result = {"ok": False, "issues": [str(exc)], "computed_items_sum": None, "computed_total": None}

    # Stage 4
    print_summary(receipt, qa_result)

    if args.json:
        print(json.dumps({"receipt": receipt, "qa": qa_result}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
