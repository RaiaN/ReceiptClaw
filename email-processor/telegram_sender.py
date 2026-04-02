"""
telegram_sender.py — format and send a parsed receipt to a Telegram group.

Responsibilities:
  - format_receipt_html : render receipt + QA result as Telegram HTML
  - build_keyboard      : per-item inline keyboard (Mine / Split 2 / All share / Skip)
  - send_receipt        : POST to Telegram Bot API, return message_id
"""

import html
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

_API = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _e(text: str) -> str:
    """HTML-escape a string for Telegram HTML parse mode."""
    return html.escape(str(text))


def _money(value, sym: str = "£") -> str:
    return f"{sym}{value:.2f}" if value is not None else "N/A"


def format_receipt_html(receipt: dict, qa: dict) -> str:
    """Render receipt + QA result as a mobile-friendly Telegram HTML message."""
    sym      = "£" if (receipt.get("currency") or "GBP") == "GBP" else receipt.get("currency", "") + " "
    merchant = _e(receipt.get("merchant") or "Tesco")
    date     = _e(receipt.get("ordered_at") or "N/A")
    payment  = _e(receipt.get("payment_method") or "N/A")
    total    = receipt.get("total")
    items    = receipt.get("items") or []
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    lines.append(f"🧾 <b>{merchant} — Receipt</b>")
    lines.append(f"📅 {date}  •  💳 {payment}  •  💰 <b>{_money(total, sym)}</b>")
    lines.append("")

    # ── Line items as a simple numbered list ─────────────────────────────────
    lines.append("<b>Items</b>")
    for idx, item in enumerate(items, start=1):
        label = _e(item.get("normalized_label") or item.get("raw_label") or "?")
        qty   = item.get("quantity")
        qty_s = f"{qty:g}× " if qty is not None else ""
        tot   = item.get("line_total")
        disc  = item.get("item_discount")
        disc_s = f"  <i>-{_money(disc, sym)}</i>" if disc else ""
        lines.append(f"{idx}. {qty_s}{label} — <b>{_money(tot, sym)}</b>{disc_s}")

    # ── Basket discounts ──────────────────────────────────────────────────────
    basket_discounts = receipt.get("basket_discounts") or []
    if basket_discounts:
        lines.append("")
        lines.append("<b>Discounts &amp; adjustments</b>")
        for bd in basket_discounts:
            amt  = bd["amount"]
            sign = "-" if amt >= 0 else "+"
            lines.append(f"• {_e(bd['description'])} — {sign}{_money(abs(amt), sym)}")

    # ── Totals ────────────────────────────────────────────────────────────────
    lines.append("")
    subtotal = receipt.get("subtotal")
    if subtotal is not None:
        lines.append(f"Basket before offers: {_money(subtotal, sym)}")

    item_savings   = sum((i.get("item_discount") or 0) for i in items)
    basket_savings = sum((b.get("amount") or 0) for b in basket_discounts)
    total_savings  = item_savings + basket_savings
    if total_savings:
        lines.append(f"Total savings: <b>-{_money(total_savings, sym)}</b>")

    delivery = receipt.get("delivery_fee")
    if delivery is not None:
        lines.append(f"Delivery: {_money(delivery, sym)}")

    lines.append(f"<b>Total paid: {_money(total, sym)}</b>")

    # ── QA status ─────────────────────────────────────────────────────────────
    lines.append("")
    if qa.get("ok"):
        lines.append("✅ <i>QA check passed — arithmetic verified</i>")
    else:
        issues = "; ".join(qa.get("issues") or ["unknown issue"])
        lines.append(f"⚠️ <i>QA failed: {_e(issues)}</i>")

    lines.append("")
    lines.append("<i>Assign each item using the buttons below:</i>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inline keyboard
# ---------------------------------------------------------------------------

def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _item_label(idx: int, item: dict) -> str:
    """Short display label for a keyboard header button: '#N name — £total'."""
    name  = (item.get("normalized_label") or item.get("raw_label") or f"Item {idx + 1}")[:28]
    total = item.get("line_total")
    sym   = "£"
    price = f" — {_money(total, sym)}" if total is not None else ""
    return f"#{idx + 1} {name}{price}"


def build_keyboard(items: list[dict]) -> list[list[dict]]:
    """
    Two rows per item:
      Row 1 — label button (non-interactive): '#N item name — £total'
      Row 2 — action buttons: Mine / Split 2 / All share / Skip
    Footer row: Done / Reset

    callback_data scheme:
      i:{idx}:m  — mine (sole ownership)
      i:{idx}:h  — half (2-way split)
      i:{idx}:a  — all share (n-way even split)
      i:{idx}:s  — skip (not mine)
      i:{idx}:info — label tap (no-op)
      done       — compute and post settlements
      reset      — clear all selections
    """
    keyboard: list[list[dict]] = []
    for idx, item in enumerate(items):
        keyboard.append([_btn(_item_label(idx, item), f"i:{idx}:info")])
        keyboard.append([
            _btn("✅ Mine",      f"i:{idx}:m"),
            _btn("½ Split 2",   f"i:{idx}:h"),
            _btn("👥 All share", f"i:{idx}:a"),
            _btn("⏭ Skip",      f"i:{idx}:s"),
        ])
    keyboard.append([
        _btn("✅ Done — settle up", "done"),
        _btn("🔄 Reset all",       "reset"),
    ])
    return keyboard


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_receipt(receipt: dict, qa: dict) -> int:
    """
    Send the formatted receipt to the configured Telegram group.
    Returns the message_id of the sent message.
    Raises RuntimeError if the token or chat ID is not configured,
    or if the Telegram API returns an error.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in email-processor/config.py")
    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set in email-processor/config.py")

    text     = format_receipt_html(receipt, qa)
    keyboard = build_keyboard(receipt.get("items") or [])

    payload = {
        "chat_id":      TELEGRAM_CHAT_ID,
        "text":         text,
        "parse_mode":   "HTML",
        "reply_markup": json.dumps({"inline_keyboard": keyboard}),
    }

    url  = _API.format(token=TELEGRAM_BOT_TOKEN, method="sendMessage")
    resp = requests.post(url, data=payload, timeout=15)
    data = resp.json()

    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data.get('description', data)}")

    return data["result"]["message_id"]
