import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.calculation.engine import LineInput, NormLine, PriceInput, ProjectParams, ResourceRef, Snapshot

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture(scope="session")
def rule_pack() -> dict:
    return json.loads((FIXTURES / "rule_pack_tt36_2026.json").read_text(encoding="utf-8"))


@pytest.fixture
def resources():
    return {
        "VL.XM": ResourceRef("VL.XM", "MATERIAL", "Xi măng PC40", "kg"),
        "VL.CAT": ResourceRef("VL.CAT", "MATERIAL", "Cát vàng", "m3"),
        "NC.3.5": ResourceRef("NC.3.5", "LABOR", "Nhân công 3,5/7", "công"),
        "M.TRON": ResourceRef("M.TRON", "MACHINE", "Máy trộn bê tông 250L", "ca"),
    }


@pytest.fixture
def prices():
    return {
        "VL.XM": PriceInput(Decimal("1500"), "release:SAMPLE:HN:2026-Q3"),
        "VL.CAT": PriceInput(Decimal("350000"), "release:SAMPLE:HN:2026-Q3"),
        "NC.3.5": PriceInput(Decimal("300000"), "release:SAMPLE:HN:2026-Q3"),
        "M.TRON": PriceInput(Decimal("250000"), "release:SAMPLE:HN:2026-Q3"),
    }


def make_line(id="L1", quantity="10", expr="", k_nc="1", k_m="1", components=None, **kw) -> LineInput:
    comps = (
        components
        if components is not None
        else [
            NormLine("VL.XM", "MATERIAL", Decimal("300")),
            NormLine("VL.CAT", "MATERIAL", Decimal("0.5")),
            NormLine(None, "MATERIAL", Decimal("2"), is_other_pct=True),
            NormLine("NC.3.5", "LABOR", Decimal("1.2")),
            NormLine("M.TRON", "MACHINE", Decimal("0.1")),
            NormLine(None, "MACHINE", Decimal("5"), is_other_pct=True),
        ]
    )
    return LineInput(
        id=id,
        item_id="I1",
        item_name="HM1",
        order=1,
        code="AF.11111",
        name="Bê tông mẫu",
        unit="m3",
        quantity_expr=expr,
        quantity=Decimal(quantity),
        k_nc=Decimal(k_nc),
        k_m=Decimal(k_m),
        components=comps,
        **kw,
    )


def make_snapshot(rule_pack, resources, prices, lines=None, **params) -> Snapshot:
    p = dict(construction_type="CIVIL")
    p.update(params)
    return Snapshot(
        lines=lines or [make_line()], resources=resources, prices=prices, rule_pack=rule_pack, params=ProjectParams(**p)
    )
