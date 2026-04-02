from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from receipt_processor.models import Discount, ParsedReceipt, money


DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y-%m-%d")
MONEY_RE = r"£\s*(\d+(?:\.\d{1,2})?)"


class TescoReceiptParser:
    SHARED_KEYWORDS = ("milk", "eggs", "bread", "loo roll", "toilet roll", "butter", "rice")

    def parse(self, text: str) -> ParsedReceipt:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        merchant = "Tesco" if "tesco" in text.lower() else "Unknown"
        ordered_at = self._parse_datetime(lines)
        subtotal = self._parse_money_field(lines, ("subtotal", "items total"), default=Decimal("0.00"))
        delivery_fee = self._parse_money_field(lines, ("delivery", "service charge"), default=Decimal("0.00"))
        total = self._parse_money_field(lines, ("total", "amount charged"), default=Decimal("0.00"))
        payment_method = self._parse_payment_method(lines)
        basket_discounts = self._parse_basket_discounts(lines)
        items = self._parse_items(lines)
        if subtotal == Decimal("0.00") and items:
            subtotal = sum((item["line_total"] for item in items), start=Decimal("0.00"))
        if total == Decimal("0.00"):
            discount_total = sum((discount.amount for discount in basket_discounts), start=Decimal("0.00"))
            total = subtotal + delivery_fee - discount_total
        return ParsedReceipt(
            merchant=merchant,
            ordered_at=ordered_at,
            currency="GBP",
            subtotal=money(subtotal),
            delivery_fee=money(delivery_fee),
            basket_discounts=basket_discounts,
            total=money(total),
            payment_method=payment_method,
            items=items,
        )

    def _parse_datetime(self, lines: list[str]) -> datetime:
        for line in lines:
            if any(token in line.lower() for token in ("ordered", "date")):
                for fmt in DATE_FORMATS:
                    match = re.search(r"(\d{1,2} [A-Za-z]{3,9} \d{4}|\d{4}-\d{2}-\d{2})", line)
                    if not match:
                        continue
                    try:
                        return datetime.strptime(match.group(1), fmt)
                    except ValueError:
                        continue
        return datetime(2026, 1, 1)

    def _parse_money_field(
        self, lines: list[str], labels: tuple[str, ...], default: Decimal
    ) -> Decimal:
        for line in lines:
            lower = line.lower()
            if any(label in lower for label in labels):
                values = re.findall(MONEY_RE, line)
                if values:
                    return money(values[-1])
        return money(default)

    def _parse_payment_method(self, lines: list[str]) -> str | None:
        for line in lines:
            if "payment" in line.lower():
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
        return None

    def _parse_basket_discounts(self, lines: list[str]) -> list[Discount]:
        discounts: list[Discount] = []
        for line in lines:
            lower = line.lower()
            if any(token in lower for token in ("discount", "clubcard", "saving", "promo")):
                values = re.findall(MONEY_RE, line)
                if values:
                    discounts.append(Discount(description=line, amount=money(values[-1])))
        return discounts

    def _parse_items(self, lines: list[str]) -> list[dict]:
        items: list[dict] = []
        item_index = 1
        for line in lines:
            if any(token in line.lower() for token in ("ordered", "subtotal", "delivery", "total", "payment", "discount", "saving")):
                continue
            match = re.match(
                r"(?P<label>.+?)\s+x(?P<qty>\d+(?:\.\d+)?)\s+£\s*(?P<total>\d+(?:\.\d{1,2})?)(?:\s+discount\s+£\s*(?P<discount>\d+(?:\.\d{1,2})?))?$",
                line,
                flags=re.I,
            )
            if match:
                label = match.group("label").strip()
                qty = money(match.group("qty"))
                total = money(match.group("total"))
                unit_price = money(total / qty) if qty else total
                item_discount = money(match.group("discount")) if match.group("discount") else None
                items.append(
                    {
                        "id": f"item-{item_index}",
                        "raw_label": label,
                        "normalized_label": self._normalize_label(label),
                        "quantity": qty,
                        "unit_price": unit_price,
                        "item_discount": item_discount,
                        "line_total": total,
                    }
                )
                item_index += 1
                continue

            match = re.match(r"(?P<label>.+?)\s+£\s*(?P<total>\d+(?:\.\d{1,2})?)$", line, flags=re.I)
            if match:
                label = match.group("label").strip()
                total = money(match.group("total"))
                items.append(
                    {
                        "id": f"item-{item_index}",
                        "raw_label": label,
                        "normalized_label": self._normalize_label(label),
                        "quantity": money("1"),
                        "unit_price": total,
                        "item_discount": None,
                        "line_total": total,
                    }
                )
                item_index += 1
        return items

    def _normalize_label(self, label: str) -> str:
        normalized = re.sub(r"\s+", " ", label).strip()
        return normalized.title()
