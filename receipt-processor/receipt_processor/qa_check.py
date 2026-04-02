from __future__ import annotations

from decimal import Decimal

from receipt_processor.models import Allocation, Order, money


class QAChecker:
    def verify(self, order: Order, allocations: list[Allocation], member_totals: dict[str, Decimal]) -> tuple[bool, str]:
        item_map = {item.id: item for item in order.items}
        recomputed = Decimal("0.00")
        for allocation in allocations:
            item = item_map[allocation.order_item_id]
            recomputed += money(item.line_total * allocation.share_value)
        fees = order.fees
        discounts = sum((discount.amount for discount in order.discounts), start=Decimal("0.00"))
        grand_total = money(recomputed + fees - discounts)
        member_total = money(sum(member_totals.values(), start=Decimal("0.00")))
        if grand_total != order.total or member_total != order.total:
            return False, f"QA mismatch: recomputed={grand_total}, member_total={member_total}, order_total={order.total}"
        return True, "QA approved"

