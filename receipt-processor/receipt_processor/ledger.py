from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from receipt_processor.models import Allocation, Order, Settlement, TWOPLACES, money, split_evenly


@dataclass
class LedgerResult:
    member_totals: dict[str, Decimal]
    settlements: list[Settlement]


class Ledger:
    def compute(self, order: Order, allocations: list[Allocation], now: datetime | None = None) -> LedgerResult:
        now = now or datetime.utcnow()
        item_map = {item.id: item for item in order.items}
        totals = defaultdict(lambda: Decimal("0.00"))
        participants: list[str] = []
        for item in order.items:
            item_allocations = [allocation for allocation in allocations if allocation.order_item_id == item.id]
            share_sum = sum((allocation.share_value for allocation in item_allocations), start=Decimal("0"))
            if abs(share_sum - Decimal("1")) > Decimal("0.000001"):
                raise ValueError(f"Item {item.id} is not fully allocated")
            split_amounts = self._split_item(item.line_total, item_allocations)
            for member_id, amount in split_amounts.items():
                totals[member_id] += amount
                if member_id not in participants:
                    participants.append(member_id)

        if participants:
            fees = split_evenly(order.fees, len(participants))
            discount_total = sum((discount.amount for discount in order.discounts), start=Decimal("0.00"))
            discounts = split_evenly(discount_total, len(participants))
            for index, member_id in enumerate(participants):
                totals[member_id] += fees[index]
                totals[member_id] -= discounts[index]

        expected_total = money(sum(totals.values(), start=Decimal("0.00")))
        if expected_total != order.total:
            raise ValueError(f"Allocations do not reconcile to order total: {expected_total} != {order.total}")

        settlements = [
            Settlement(
                order_id=order.id,
                debtor_member_id=member_id,
                creditor_member_id=order.payer_member_id,
                amount=money(amount),
                status="pending",
            )
            for member_id, amount in totals.items()
            if member_id != order.payer_member_id and amount > Decimal("0.00")
        ]
        order.status = "settled" if settlements else "paid_confirmed"
        order.balances_posted_at = now
        return LedgerResult(member_totals={key: money(value) for key, value in totals.items()}, settlements=settlements)

    def _split_item(self, line_total: Decimal, item_allocations: list[Allocation]) -> dict[str, Decimal]:
        raw_values = [money(line_total * allocation.share_value) for allocation in item_allocations]
        delta = line_total - sum(raw_values, start=Decimal("0.00"))
        adjusted_values = list(raw_values)
        index = 0
        while delta != Decimal("0.00"):
            step = TWOPLACES if delta > 0 else -TWOPLACES
            adjusted_values[index] += step
            delta -= step
            index += 1
        return {
            allocation.member_id: adjusted_values[i]
            for i, allocation in enumerate(item_allocations)
        }
