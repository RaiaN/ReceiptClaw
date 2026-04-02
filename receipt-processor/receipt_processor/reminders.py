from __future__ import annotations

from datetime import datetime, timedelta

from receipt_processor.models import Order, Settlement


class ReminderEngine:
    def payment_chaser(self, order: Order, settlements: list[Settlement], now: datetime) -> list[str]:
        if not settlements or all(settlement.status == "paid" for settlement in settlements):
            return []
        if not order.balances_posted_at or now < order.balances_posted_at + timedelta(hours=24):
            return []
        messages = []
        for settlement in settlements:
            if settlement.status != "paid":
                messages.append(
                    f"Reminder: {settlement.debtor_member_id} owes {settlement.creditor_member_id} GBP {settlement.amount} for order {order.id}."
                )
        return messages

    def grocery_gap_reminder(
        self,
        orders: list[Order],
        now: datetime,
        suppression_replies: list[str] | None = None,
    ) -> str | None:
        suppression_replies = suppression_replies or []
        latest_order = max((order.ordered_at for order in orders), default=None)
        if not latest_order:
            return "Group reminder: nobody has logged a grocery order yet."
        if any(reply.strip().lower() == "already ordered" for reply in suppression_replies):
            latest = max(orders, key=lambda order: order.ordered_at)
            latest.grocery_nudge_suppressed_until = now + timedelta(hours=48)
            return None
        if any(order.grocery_nudge_suppressed_until and now < order.grocery_nudge_suppressed_until for order in orders):
            return None
        if now >= latest_order + timedelta(days=5):
            latest = max(orders, key=lambda order: order.ordered_at)
            latest.last_grocery_nudge_at = now
            return "Group reminder: no new Tesco order has been logged in the last 5 days."
        return None

