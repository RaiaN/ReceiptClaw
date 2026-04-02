from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from receipt_processor.chat_orchestrator import ChatEvent, ChatOrchestrator
from receipt_processor.demo import build_household, order_from_text
from receipt_processor.ledger import Ledger
from receipt_processor.models import Allocation
from receipt_processor.qa_check import QAChecker
from receipt_processor.receipt_ingest import EmailInboxAdapter
from receipt_processor.reminders import ReminderEngine
from receipt_processor.storage import JsonLedgerStore


class BillingFlowTests(unittest.TestCase):
    def test_single_payer_order_reconciles_exactly(self) -> None:
        household = build_household()
        order = order_from_text(
            "order-clear",
            "alice",
            """Tesco Online
Ordered: 15 Mar 2026
Coke Zero x1 £2.00
Chicken Thighs x1 £5.00
Milk x1 £1.80
Eggs x1 £2.40
Delivery £3.00
Clubcard saving £1.20
Total £13.00
""",
        )
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
        result = Ledger().compute(order, allocations, now=datetime(2026, 3, 16, 12, 0, 0))
        ok, _ = QAChecker().verify(order, allocations, result.member_totals)

        self.assertTrue(ok)
        self.assertEqual(sum(result.member_totals.values()), order.total)
        self.assertEqual(order.status, "settled")

    def test_messy_order_can_be_resolved_in_chat(self) -> None:
        household = build_household()
        order = order_from_text(
            "order-messy",
            "bob",
            """Tesco Online
Ordered: 18 Mar 2026
Pesto Pasta x1 £3.50
Mystery Snack x1 £2.10
Toilet Roll x1 £4.20
Delivery £1.20
Total £11.00
""",
        )
        orchestrator = ChatOrchestrator()
        _, proposals = orchestrator.propose_allocations(household, order)
        self.assertTrue(any(item.allocation_status == "unresolved" for item in order.items))

        allocations = orchestrator.apply_replies(
            household,
            order,
            proposals,
            [
                ChatEvent("alice", "mine: pesto pasta"),
                ChatEvent("cara", "mine: mystery snack"),
                ChatEvent("bob", "split 3: toilet roll"),
            ],
        )
        result = Ledger().compute(order, allocations, now=datetime(2026, 3, 18, 12, 0, 0))
        ok, message = QAChecker().verify(order, allocations, result.member_totals)

        self.assertTrue(ok, message)
        self.assertEqual(order.status, "settled")
        self.assertEqual(sum(result.member_totals.values()), order.total)

    def test_multiple_outstanding_orders_only_chase_unpaid_settled_order(self) -> None:
        household = build_household()
        settled_order = order_from_text(
            "order-unpaid",
            "alice",
            """Tesco Online
Ordered: 10 Mar 2026
Chicken Thighs x1 £6.00
Milk x1 £1.50
Delivery £1.50
Total £9.00
""",
        )
        orchestrator = ChatOrchestrator()
        _, proposals = orchestrator.propose_allocations(household, settled_order)
        allocations = orchestrator.apply_replies(
            household,
            settled_order,
            proposals,
            [
                ChatEvent("bob", "mine: chicken thighs"),
                ChatEvent("cara", "mine: milk"),
            ],
        )
        result = Ledger().compute(settled_order, allocations, now=datetime(2026, 3, 10, 8, 0, 0))
        for settlement in result.settlements:
            settlement.status = "paid"

        unpaid_order = order_from_text(
            "order-chase",
            "alice",
            """Tesco Online
Ordered: 12 Mar 2026
Steak x1 £8.00
Bread x1 £1.00
Delivery £1.00
Total £10.00
""",
        )
        _, proposals_2 = orchestrator.propose_allocations(household, unpaid_order)
        allocations_2 = orchestrator.apply_replies(
            household,
            unpaid_order,
            proposals_2,
            [
                ChatEvent("bob", "mine: steak"),
                ChatEvent("cara", "mine: bread"),
            ],
        )
        result_2 = Ledger().compute(unpaid_order, allocations_2, now=datetime(2026, 3, 12, 8, 0, 0))

        partial_order = order_from_text(
            "order-partial",
            "bob",
            """Tesco Online
Ordered: 14 Mar 2026
Rice x1 £2.00
Unknown Item x1 £3.00
Delivery £1.00
Total £6.00
""",
        )
        _, proposals_3 = orchestrator.propose_allocations(household, partial_order)
        partial_allocations = orchestrator.apply_replies(
            household,
            partial_order,
            proposals_3,
            [ChatEvent("alice", "split 2: rice")],
        )

        reminders = ReminderEngine().payment_chaser(
            unpaid_order,
            result_2.settlements,
            now=datetime(2026, 3, 13, 9, 0, 0),
        )
        no_paid_reminder = ReminderEngine().payment_chaser(
            settled_order,
            result.settlements,
            now=datetime(2026, 3, 13, 9, 0, 0),
        )

        self.assertTrue(reminders)
        self.assertFalse(no_paid_reminder)
        self.assertEqual(partial_order.status, "resolving")
        self.assertTrue(any(settlement.status == "pending" for settlement in result_2.settlements))
        self.assertTrue(partial_allocations)

    def test_email_adapter_extracts_body_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            eml_path = Path(temp_dir) / "sample.eml"
            eml_path.write_text(
                "Subject: Tesco receipt\n"
                "Content-Type: text/html; charset=UTF-8\n\n"
                "<html><body><p>Tesco Online</p><p>Ordered: 15 Mar 2026</p><p>Milk x1 £1.50</p><p>Total £1.50</p></body></html>"
            )
            payload = EmailInboxAdapter(eml_path).read()
            self.assertIn("Milk x1 £1.50", payload.raw_content)

    def test_grocery_gap_reminder_and_suppression(self) -> None:
        household = build_household()
        order = order_from_text(
            "order-latest",
            "alice",
            """Tesco Online
Ordered: 10 Mar 2026
Milk x1 £1.50
Total £1.50
""",
        )
        reminder = ReminderEngine().grocery_gap_reminder([order], now=datetime(2026, 3, 16, 10, 0, 0))
        suppressed = ReminderEngine().grocery_gap_reminder(
            [order],
            now=datetime(2026, 3, 16, 12, 0, 0),
            suppression_replies=["already ordered"],
        )
        self.assertIsNotNone(reminder)
        self.assertIsNone(suppressed)

    def test_store_writes_snapshot(self) -> None:
        household = build_household()
        order = order_from_text(
            "order-store",
            "alice",
            """Tesco Online
Ordered: 15 Mar 2026
Milk x1 £1.50
Total £1.50
""",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ledger.json"
            JsonLedgerStore(path).save(household, [order], [], [])
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
