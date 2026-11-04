from decimal import Decimal

import pytest

from apps.calculation.engine import run
from apps.calculation.engine.core import _pick_column

from .conftest import make_snapshot


def test_golden_civil_under_40bn(rule_pack, resources, prices):
    """Tính tay: T = 10,237,500 (1 dòng × 10 m3). Dân dụng, ≤40 tỷ → C 7,3%, TT 2,5%, TL 5,5%, VAT 10%, nhà tạm 1,1%."""
    snap = make_snapshot(rule_pack, resources, prices, approved_construction_cost_bn=Decimal("12"))
    res = run(snap)
    v = {k: Decimal(x) for k, x in res.summary["values"].items()}
    assert v["VL"] == Decimal("6375000") and v["NC"] == Decimal("3600000") and v["M"] == Decimal("262500")
    assert v["T"] == Decimal("10237500")
    assert v["C"] == Decimal("747338")  # 10237500 × 7.3% = 747337.5 → half-up 747338
    assert v["TT"] == Decimal("255938")  # × 2.5% = 255937.5
    assert v["GT"] == Decimal("1003276")
    assert v["TL"] == Decimal("618243")  # (10237500 + 1003276) × 5.5% = 618242.68
    assert v["GXDTT"] == Decimal("11859019")
    assert v["GTGT"] == Decimal("1185902")  # 1185901.9
    assert v["GXD"] == Decimal("13044921")
    assert v["LT"] == Decimal("130449")  # 11859019 × 1.1% = 130449.209
    assert v["LT_GTGT"] == Decimal("13045")
    assert v["TONG"] == v["GXD"] + v["LT"] + v["LT_GTGT"]
    assert res.summary["overhead"]["column"] == 0 and res.summary["overhead"]["rate_pct"] == "7.3"
    assert "RULE_PACK_NOT_APPROVED" in {w.code for w in res.warnings}


@pytest.mark.parametrize(
    "basis,col",
    [("40", 0), ("40.001", 1), ("60", 1), ("100", 2), ("300", 3), ("500", 4), ("750", 5), ("1000", 6), ("1000.5", 7)],
)
def test_threshold_boundaries_bang_3_3(rule_pack, basis, col):
    assert _pick_column(rule_pack["overhead_direct"]["thresholds_bn"], Decimal(basis)) == col


def test_remote_area_coeff_1_1(rule_pack, resources, prices):
    snap = make_snapshot(rule_pack, resources, prices, approved_construction_cost_bn=Decimal("12"), is_remote_area=True)
    res = run(snap)
    assert res.summary["overhead"]["rate_pct"] == "8.03"  # 7.3 × 1.1
    assert Decimal(res.summary["values"]["C"]) == Decimal("822071")  # 10237500 × 8.03% = 822071.25


def test_overhead_on_labor_bang_3_4(rule_pack, resources, prices):
    snap = make_snapshot(
        rule_pack,
        resources,
        prices,
        construction_type="EQUIPMENT_INSTALL",
        overhead_basis="LABOR",
        labor_overhead_row="EQUIPMENT_INSTALL",
        approved_construction_cost_bn=Decimal("5"),
    )
    res = run(snap)
    oh = res.summary["overhead"]
    assert oh["table"] == "3.4" and oh["column"] == 0 and oh["rate_pct"] == "65"
    assert Decimal(res.summary["values"]["C"]) == Decimal("2340000")  # NC 3,600,000 × 65%
    assert res.summary["rows"][7]["rate_pct"] == "6.0"  # TNCTTT lắp đặt thiết bị = 6,0


def test_feasibility_report_uses_first_column(rule_pack, resources, prices):
    snap = make_snapshot(
        rule_pack, resources, prices, is_feasibility_report_only=True, approved_construction_cost_bn=Decimal("900")
    )
    assert run(snap).summary["overhead"]["column"] == 0


def test_derived_threshold_when_no_approved_cost(rule_pack, resources, prices):
    snap = make_snapshot(rule_pack, resources, prices)
    res = run(snap)
    assert "THRESHOLD_BASIS_DERIVED" in {w.code for w in res.warnings}
    assert res.summary["overhead"]["column"] == 0


def test_linear_temp_housing_and_vat_override(rule_pack, resources, prices):
    snap = make_snapshot(
        rule_pack,
        resources,
        prices,
        is_linear=True,
        approved_construction_cost_bn=Decimal("200"),
        vat_rate=Decimal("0.08"),
    )
    res = run(snap)
    assert res.summary["temp_housing"]["rate_pct"] == "1.9"
    assert res.summary["vat_rate"] == "0.08"
    v = res.summary["values"]
    assert Decimal(v["GTGT"]) == (Decimal(v["GXDTT"]) * Decimal("0.08")).quantize(Decimal("1"))


def test_all_construction_types_have_rates(rule_pack, resources, prices):
    for ct in rule_pack["overhead_direct"]["rows"]:
        snap = make_snapshot(
            rule_pack, resources, prices, construction_type=ct, approved_construction_cost_bn=Decimal("50")
        )
        assert run(snap).summary["values"]["GXDTT"]
