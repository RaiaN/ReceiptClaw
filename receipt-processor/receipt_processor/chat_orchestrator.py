from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from receipt_processor.models import Allocation, Household, Member, Order, OrderItem, money


SHARED_KEYWORDS = ("milk", "eggs", "bread", "loo roll", "toilet roll", "butter", "rice")


@dataclass
class ChatEvent:
    member_id: str
    text: str


class ChatOrchestrator:
    def propose_allocations(self, household: Household, order: Order) -> tuple[list[str], list[Allocation]]:
        messages = [
            f"Order {order.id}: {order.merchant} on {order.ordered_at.date()} total {order.currency} {order.total}",
            "Reply with `mine: ...`, `split 2: ...`, `split 3: ...`, `paid`, or `already ordered`.",
        ]
        allocations: list[Allocation] = []
        for item in order.items:
            if self._is_shared_candidate(item):
                participants = household.members[:2] if len(household.members) >= 2 else household.members
                allocations.extend(self._allocate_split(item, participants))
                item.allocation_status = "proposed"
            else:
                item.allocation_status = "unresolved"
        return messages, allocations

    def apply_replies(
        self,
        household: Household,
        order: Order,
        existing_allocations: list[Allocation],
        replies: list[ChatEvent],
    ) -> list[Allocation]:
        allocations = [allocation for allocation in existing_allocations if allocation.order_item_id in {item.id for item in order.items}]
        name_map = {member.display_name.lower(): member for member in household.members}
        for reply in replies:
            text = reply.text.strip().lower()
            if text == "paid":
                order.status = "paid_confirmed"
                continue
            if text == "already ordered":
                continue
            if ":" not in text:
                continue
            command, raw_items = text.split(":", 1)
            item_names = [name.strip() for name in raw_items.split(",") if name.strip()]
            matched_items = [item for item in order.items if any(name in item.normalized_label.lower() for name in item_names)]
            allocations = [allocation for allocation in allocations if allocation.order_item_id not in {item.id for item in matched_items}]
            if command == "mine":
                member = self._member_by_id(household, reply.member_id)
                for item in matched_items:
                    allocations.append(Allocation(item.id, member.id, "fixed_fraction", Decimal("1")))
                    item.allocation_status = "allocated"
            elif command.startswith("split"):
                parts = command.split()
                requested = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else len(household.members)
                participants = household.members[:requested]
                for item in matched_items:
                    allocations.extend(self._allocate_split(item, participants))
                    item.allocation_status = "allocated"
            elif command.startswith("assign"):
                _, _, display_name = command.partition(" ")
                member = name_map.get(display_name.strip())
                if member:
                    for item in matched_items:
                        allocations.append(Allocation(item.id, member.id, "fixed_fraction", Decimal("1")))
                        item.allocation_status = "allocated"
        for item in order.items:
            if item.id in {allocation.order_item_id for allocation in allocations} and item.allocation_status == "unresolved":
                item.allocation_status = "allocated"
        if all(item.allocation_status in {"allocated", "proposed"} for item in order.items):
            order.status = "resolved"
        else:
            order.status = "resolving"
        return allocations

    def _allocate_split(self, item: OrderItem, participants: list[Member]) -> list[Allocation]:
        if not participants:
            return []
        share = Decimal("1") / Decimal(len(participants))
        return [
            Allocation(order_item_id=item.id, member_id=member.id, share_type="fixed_fraction", share_value=share)
            for member in participants
        ]

    def _is_shared_candidate(self, item: OrderItem) -> bool:
        label = item.normalized_label.lower()
        return any(keyword in label for keyword in SHARED_KEYWORDS)

    def _member_by_id(self, household: Household, member_id: str) -> Member:
        for member in household.members:
            if member.id == member_id:
                return member
        raise KeyError(f"Unknown member {member_id}")

