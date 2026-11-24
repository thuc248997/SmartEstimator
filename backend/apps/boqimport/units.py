"""Chuẩn hóa đơn vị và quy đổi khối lượng BoQ sang đơn vị của định mức.

BoQ bóc từ bản vẽ thường ghi "m3", "m2", "kg"; định mức TT 38 lại tính theo "100m3", "1m2", "1 tấn"…
Ta tách đơn vị thành (hệ số, gốc): "100m3 đất nguyên thổ" → (100, "m3"); "1 tấn" → (1, "tan").
Hệ số quy đổi = hệ số BoQ × (kg→tấn nếu có) ÷ hệ số định mức.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

_SUPERSCRIPT = str.maketrans({"³": "3", "²": "2"})

# Gốc đơn vị → (gốc chuẩn, hệ số so với gốc chuẩn)
_BASES: dict[str, tuple[str, Decimal]] = {
    "m3": ("m3", Decimal(1)),
    "m2": ("m2", Decimal(1)),
    "m": ("m", Decimal(1)),
    "md": ("m", Decimal(1)),
    "km": ("m", Decimal(1000)),
    "tan": ("tan", Decimal(1)),
    "t": ("tan", Decimal(1)),
    "kg": ("tan", Decimal("0.001")),
    "ha": ("ha", Decimal(1)),
    # Đơn vị đếm (cái / chiếc / bộ / tủ / thiết bị…) coi là cùng loại, 1 : 1
    "cai": ("cai", Decimal(1)),
    "chiec": ("cai", Decimal(1)),
    "bo": ("cai", Decimal(1)),
    "tu": ("cai", Decimal(1)),
    "con": ("cai", Decimal(1)),
    "thiet bi": ("cai", Decimal(1)),
    "may": ("cai", Decimal(1)),
    "module": ("cai", Decimal(1)),
    "cum": ("cai", Decimal(1)),
    "dau": ("cai", Decimal(1)),
    "cong": ("cong", Decimal(1)),
    "ca": ("ca", Decimal(1)),
    "lit": ("lit", Decimal(1)),
    "coc": ("coc", Decimal(1)),
    "cau kien": ("cau kien", Decimal(1)),
    "moi noi": ("moi noi", Decimal(1)),
    "diem": ("diem", Decimal(1)),
    "hop": ("cai", Decimal(1)),
    "cuon": ("cuon", Decimal(1)),
    "tam": ("tam", Decimal(1)),
    "vien": ("vien", Decimal(1)),
    "chi tieu": ("chi tieu", Decimal(1)),
    "mau": ("mau", Decimal(1)),
    "tru": ("tru", Decimal(1)),
    "kw": ("kw", Decimal(1)),
}


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


@dataclass(frozen=True)
class Unit:
    factor: Decimal  # số đơn vị gốc chuẩn trong 1 đơn vị này (vd 100m3 → 100; kg → 0.001 tấn)
    base: str  # gốc chuẩn ("m3", "tan"…); "" nếu không nhận ra


_LEAD = re.compile(r"^\s*(\d+(?:[.,]\d+)?)?\s*(.*)$")


def parse_unit(raw: str | None) -> Unit:
    s = strip_accents((raw or "").translate(_SUPERSCRIPT)).lower().strip()
    s = s.replace("/1km", "").strip()
    m = _LEAD.match(s)
    num = Decimal(1)
    rest = s
    if m:
        if m.group(1):
            num = Decimal(m.group(1).replace(",", "."))
        rest = m.group(2).strip()
    rest = re.sub(r"[()]", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip()
    # Ghép dài nhất trước: "cau kien", "moi noi", "m3 dat nguyen tho" → m3
    for key in sorted(_BASES, key=len, reverse=True):
        if rest == key or rest.startswith(key + " ") or rest.startswith(key + "/"):
            base, f = _BASES[key]
            return Unit(num * f, base)
    return Unit(num, rest)


def conversion_factor(boq_unit: str, norm_unit: str) -> Decimal | None:
    """Khối lượng theo định mức = khối lượng BoQ × hệ số. None nếu hai đơn vị không cùng loại."""
    a, b = parse_unit(boq_unit), parse_unit(norm_unit)
    if not a.base or not b.base or a.base != b.base:
        return None
    return a.factor / b.factor
