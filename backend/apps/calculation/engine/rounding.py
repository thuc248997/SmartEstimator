from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

_MODES = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN}


@dataclass(frozen=True)
class RoundingPolicy:
    quantity: int = 3
    norm_consumption: int = 4
    unit_price: int = 0
    amount: int = 0
    mode: str = "ROUND_HALF_UP"

    @classmethod
    def from_dict(cls, d: dict | None) -> RoundingPolicy:
        d = d or {}
        return cls(
            quantity=int(d.get("quantity", 3)),
            norm_consumption=int(d.get("norm_consumption", 4)),
            unit_price=int(d.get("unit_price", 0)),
            amount=int(d.get("amount", 0)),
            mode=str(d.get("mode", "ROUND_HALF_UP")),
        )

    def _q(self, value: Decimal, places: int) -> Decimal:
        exp = Decimal(1).scaleb(-places)  # 10**-places
        return value.quantize(exp, rounding=_MODES[self.mode])

    def qty(self, v: Decimal) -> Decimal:
        return self._q(v, self.quantity)

    def consumption(self, v: Decimal) -> Decimal:
        return self._q(v, self.norm_consumption)

    def price(self, v: Decimal) -> Decimal:
        return self._q(v, self.unit_price)

    def money(self, v: Decimal) -> Decimal:
        return self._q(v, self.amount)
