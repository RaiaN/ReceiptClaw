from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from receipt_processor.models import Allocation, Household, Order, Settlement


class JsonLedgerStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(
        self,
        household: Household,
        orders: Iterable[Order],
        allocations: Iterable[Allocation],
        settlements: Iterable[Settlement],
    ) -> None:
        payload = {
            "household": {
                "id": household.id,
                "name": household.name,
                "members": [member.__dict__ for member in household.members],
            },
            "orders": [order.to_dict() for order in orders],
            "allocations": [allocation.to_dict() for allocation in allocations],
            "settlements": [settlement.to_dict() for settlement in settlements],
        }
        self.path.write_text(json.dumps(payload, indent=2))

