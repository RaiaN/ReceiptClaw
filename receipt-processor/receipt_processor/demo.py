from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from receipt_processor.chat_orchestrator import ChatEvent, ChatOrchestrator
from receipt_processor.ledger import Ledger
from receipt_processor.models import Allocation, Discount, Household, Member, Order, OrderItem
from receipt_processor.qa_check import QAChecker
from receipt_processor.receipt_ingest import ManualTextInput
from receipt_processor.receipt_parser import TescoReceiptParser
from receipt_processor.reminders import ReminderEngine
from receipt_processor.storage import JsonLedgerStore


def build_household() -> Household:
    return Household(
        id="house-1",
        name="Hack House",
        members=[
            Member(id="alice", display_name="Alice", chat_user_id="alice"),
            Member(id="bob", display_name="Bob", chat_user_id="bob"),
            Member(id="cara", display_name="Cara", chat_user_id="cara"),
        ],
    )


def order_from_text(order_id: str, payer_member_id: str, text: str) -> Order:
    parsed = TescoReceiptParser().parse(ManualTextInput(text).read().raw_content)
    items = [
        OrderItem(
            id=item["id"],
            order_id=order_id,
            raw_label=item["raw_label"],
            normalized_label=item["normalized_label"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            line_total=item["line_total"],
            item_discount=item["item_discount"],
        )
        for item in parsed.items
    ]
    return Order(
        id=order_id,
        source="manual_text_input",
        merchant=parsed.merchant,
        ordered_at=parsed.ordered_at,
        payer_member_id=payer_member_id,
        currency=parsed.currency,
        subtotal=parsed.subtotal,
        fees=parsed.delivery_fee,
        discounts=parsed.basket_discounts,
        total=parsed.total,
        status="ingested",
        items=items,
    )


def run_demo() -> dict:
    household = build_household()
    receipt_text = """Tesco Online
Ordered: 15 Mar 2026
Coke Zero x1 £2.00
Chicken Thighs x1 £5.00
Milk x1 £1.80
Eggs x1 £2.40
Delivery £3.00
Clubcard saving £1.20
Total £13.00
Payment: Visa
"""
    order = order_from_text("order-1", "alice", receipt_text)
    orchestrator = ChatOrchestrator()
    _, proposals = orchestrator.propose_allocations(household, order)
    allocations = orchestrator.apply_replies(
        household,
        order,
        proposals,
        [
            ChatEvent("alice", "mine: coke zero"),
            ChatEvent("bob", "mine: chicken thighs"),
            ChatEvent("cara", "split 3: milk, eggs"),
        ],
    )
    ledger_result = Ledger().compute(order, allocations, now=datetime(2026, 3, 16, 12, 0, 0))
    qa_ok, qa_message = QAChecker().verify(order, allocations, ledger_result.member_totals)
    reminders = ReminderEngine().payment_chaser(
        order,
        ledger_result.settlements,
        now=datetime(2026, 3, 17, 12, 1, 0),
    )
    store = JsonLedgerStore(Path(__file__).resolve().parent.parent / "demo-ledger.json")
    store.save(household, [order], allocations, ledger_result.settlements)
    return {
        "order_status": order.status,
        "member_totals": {member_id: str(amount) for member_id, amount in ledger_result.member_totals.items()},
        "settlements": [settlement.to_dict() for settlement in ledger_result.settlements],
        "qa_ok": qa_ok,
        "qa_message": qa_message,
        "reminders": reminders,
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2))

