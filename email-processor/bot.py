#!/usr/bin/env python3
"""
bot.py — Telegram callback handler for receipt item ownership triage.

Run alongside process_eml.py (long-lived polling process):
    python email-processor/bot.py

Button callback_data scheme (set by telegram_sender.build_keyboard):
    i:{item_idx}:{action}   action: m=mine, h=half(2-way), a=all-share, s=skip
    done                    compute settlements and post reply
    reset                   clear all selections for this message

In-memory state per message_id:
    state[message_id] = {
        "items":       [...],   # original receipt items list
        "receipt":     {...},   # full receipt dict (for totals)
        "allocations": {        # item_idx -> {"action": str, "user": str}
            0: {"action": "m", "user": "pete"},
            ...
        },
    }
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import Application, CallbackQueryHandler, ContextTypes
except ImportError:
    print(
        "python-telegram-bot not installed. Run: pip install python-telegram-bot",
        file=sys.stderr,
    )
    sys.exit(1)

from config import TELEGRAM_BOT_TOKEN
from telegram_sender import _item_label, _money, build_keyboard

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# message_id → {items, receipt, allocations}
state: dict[int, dict] = {}

_ACTION_LABEL = {"m": "✅ Mine", "h": "½ Split 2", "a": "👥 All", "s": "⏭ Skip"}


# ---------------------------------------------------------------------------
# State registration — called by telegram_sender after send_receipt
# ---------------------------------------------------------------------------

def register_message(message_id: int, receipt: dict) -> None:
    """Store receipt state so the bot can handle callbacks for this message."""
    state[message_id] = {
        "items":       receipt.get("items") or [],
        "receipt":     receipt,
        "allocations": {},
    }


# ---------------------------------------------------------------------------
# Keyboard builder with current allocation state reflected in button labels
# ---------------------------------------------------------------------------

def _build_stateful_keyboard(
    items: list[dict], allocations: dict[int, dict]
) -> InlineKeyboardMarkup:
    """
    Two rows per item, matching build_keyboard in telegram_sender.py:
      Row 1 — label showing item name + current assignment (if any)
      Row 2 — action buttons (or Change button if already assigned)
    """
    keyboard: list[list[InlineKeyboardButton]] = []
    for idx, item in enumerate(items):
        alloc = allocations.get(idx)

        if alloc:
            action_label = _ACTION_LABEL.get(alloc["action"], "?")
            label_text   = f"#{idx + 1} {action_label} — @{alloc['user']}"
            keyboard.append([InlineKeyboardButton(label_text, callback_data=f"i:{idx}:info")])
            keyboard.append([InlineKeyboardButton("↩ Change assignment", callback_data=f"i:{idx}:clear")])
        else:
            keyboard.append([InlineKeyboardButton(_item_label(idx, item), callback_data=f"i:{idx}:info")])
            keyboard.append([
                InlineKeyboardButton("✅ Mine",      callback_data=f"i:{idx}:m"),
                InlineKeyboardButton("½ Split 2",   callback_data=f"i:{idx}:h"),
                InlineKeyboardButton("👥 All share", callback_data=f"i:{idx}:a"),
                InlineKeyboardButton("⏭ Skip",      callback_data=f"i:{idx}:s"),
            ])

    keyboard.append([
        InlineKeyboardButton("✅ Done — settle up", callback_data="done"),
        InlineKeyboardButton("🔄 Reset all",        callback_data="reset"),
    ])
    return InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Settlement computation
# ---------------------------------------------------------------------------

def _compute_settlements(msg_state: dict) -> str:
    """Return a settlement summary string for posting as a reply."""
    receipt     = msg_state["receipt"]
    items       = msg_state["items"]
    allocations = msg_state["allocations"]
    sym         = "£" if (receipt.get("currency") or "GBP") == "GBP" else receipt.get("currency", "") + " "

    # Per-user personal totals
    personal: dict[str, float] = {}
    shared_total = 0.0
    shared_users: set[str] = set()

    for idx, item in enumerate(items):
        line_total = item.get("line_total") or 0.0
        alloc      = allocations.get(idx)
        if alloc is None or alloc["action"] == "s":
            continue
        user   = alloc["user"]
        action = alloc["action"]
        if action == "m":
            personal[user] = personal.get(user, 0.0) + line_total
        elif action in ("h", "a"):
            shared_total += line_total
            shared_users.add(user)

    # Even-split of shared items + delivery + basket discounts
    delivery      = receipt.get("delivery_fee") or 0.0
    basket_disc   = sum(b.get("amount") or 0 for b in (receipt.get("basket_discounts") or []))
    shared_pool   = shared_total + delivery - basket_disc

    if shared_users:
        per_person_shared = shared_pool / len(shared_users)
    else:
        per_person_shared = 0.0

    all_users = set(personal.keys()) | shared_users
    totals: dict[str, float] = {}
    for user in all_users:
        totals[user] = personal.get(user, 0.0) + (per_person_shared if user in shared_users else 0.0)

    if not totals:
        return "⚠️ No items were assigned — nothing to settle."

    # Assume the first person to tap "Mine" is the payer; otherwise alphabetical first
    payer = min(totals, key=lambda u: u)

    lines = ["<b>💸 Settlement Summary</b>", ""]
    for user, amount in sorted(totals.items()):
        lines.append(f"  @{user}: {_money(amount, sym)}")
    lines.append("")

    for user, amount in sorted(totals.items()):
        if user == payer:
            continue
        owes = round(amount, 2)
        lines.append(f"  👉 @{user} owes @{payer} <b>{_money(owes, sym)}</b>")

    total_check = receipt.get("total")
    if total_check is not None:
        computed = round(sum(totals.values()), 2)
        if abs(computed - total_check) < 0.02:
            lines.append("")
            lines.append("✅ <i>Totals reconcile with order total</i>")
        else:
            lines.append("")
            lines.append(
                f"⚠️ <i>Computed {_money(computed, sym)} vs order total {_money(total_check, sym)} — "
                f"some items may be unassigned</i>"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    await query.answer()

    message_id = query.message.message_id
    user       = query.from_user.username or query.from_user.first_name or "unknown"
    data       = query.data

    # Auto-register if the bot was restarted and lost state
    if message_id not in state:
        await query.answer("⚠️ Bot was restarted — please re-send the receipt.", show_alert=True)
        return

    msg_state   = state[message_id]
    items       = msg_state["items"]
    allocations = msg_state["allocations"]

    if data == "reset":
        allocations.clear()
        keyboard = _build_stateful_keyboard(items, allocations)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    if data == "done":
        summary = _compute_settlements(msg_state)
        await query.message.reply_html(summary)
        return

    if data.startswith("i:"):
        parts = data.split(":")
        if len(parts) != 3:
            return
        idx    = int(parts[1])
        action = parts[2]

        if action == "info":
            return
        if action == "clear":
            allocations.pop(idx, None)
        else:
            allocations[idx] = {"action": action, "user": user}

        keyboard = _build_stateful_keyboard(items, allocations)
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard)
        except Exception as exc:
            log.warning("edit_message_reply_markup failed: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set in email-processor/config.py", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("Bot starting — polling for updates …")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
