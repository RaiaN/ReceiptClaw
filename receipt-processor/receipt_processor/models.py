from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


TWOPLACES = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def split_evenly(total: Decimal, count: int) -> list[Decimal]:
    if count <= 0:
        return []
    base = (total / count).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    values = [base for _ in range(count)]
    delta = total - sum(values, start=Decimal("0.00"))
    index = 0
    step = TWOPLACES if delta >= 0 else -TWOPLACES
    while delta != Decimal("0.00"):
        values[index] += step
        delta -= step
        index += 1
    return values


@dataclass
class Household:
    id: str
    name: str
    members: list["Member"]


@dataclass
class Member:
    id: str
    display_name: str
    chat_user_id: str
    default_split_group: list[str] | None = None


@dataclass
class Discount:
    description: str
    amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["amount"] = str(self.amount)
        return data


@dataclass
class OrderItem:
    id: str
    order_id: str
    raw_label: str
    normalized_label: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    allocation_status: str = "unresolved"
    item_discount: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("quantity", "unit_price", "line_total", "item_discount"):
            if data[key] is not None:
                data[key] = str(data[key])
        return data


@dataclass
class Order:
    id: str
    source: str
    merchant: str
    ordered_at: datetime
    payer_member_id: str
    currency: str
    subtotal: Decimal
    fees: Decimal
    discounts: list[Discount]
    total: Decimal
    status: str
    items: list[OrderItem] = field(default_factory=list)
    balances_posted_at: datetime | None = None
    last_grocery_nudge_at: datetime | None = None
    grocery_nudge_suppressed_until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ordered_at"] = self.ordered_at.isoformat()
        data["subtotal"] = str(self.subtotal)
        data["fees"] = str(self.fees)
        data["total"] = str(self.total)
        data["discounts"] = [discount.to_dict() for discount in self.discounts]
        data["items"] = [item.to_dict() for item in self.items]
        if self.balances_posted_at:
            data["balances_posted_at"] = self.balances_posted_at.isoformat()
        if self.last_grocery_nudge_at:
            data["last_grocery_nudge_at"] = self.last_grocery_nudge_at.isoformat()
        if self.grocery_nudge_suppressed_until:
            data["grocery_nudge_suppressed_until"] = self.grocery_nudge_suppressed_until.isoformat()
        return data


@dataclass
class Allocation:
    order_item_id: str
    member_id: str
    share_type: str
    share_value: Decimal

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["share_value"] = str(self.share_value)
        return data


@dataclass
class Settlement:
    order_id: str
    debtor_member_id: str
    creditor_member_id: str
    amount: Decimal
    status: str
    confirmed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["amount"] = str(self.amount)
        if self.confirmed_at:
            data["confirmed_at"] = self.confirmed_at.isoformat()
        return data


@dataclass
class ReceiptPayload:
    source: str
    raw_content: str


@dataclass
class ParsedReceipt:
    merchant: str
    ordered_at: datetime
    currency: str
    subtotal: Decimal
    delivery_fee: Decimal
    basket_discounts: list[Discount]
    total: Decimal
    payment_method: str | None
    items: list[dict[str, Any]]

