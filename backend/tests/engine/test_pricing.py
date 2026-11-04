from decimal import Decimal

from apps.calculation.engine import run
from apps.calculation.engine.core import price_line
from apps.calculation.engine.rounding import RoundingPolicy
from apps.calculation.engine.snapshot import NormLine, PriceInput

from .conftest import make_line, make_snapshot


def test_unit_prices_follow_formulas_4_1_to_4_4(rule_pack, resources, prices):
    snap = make_snapshot(rule_pack, resources, prices)
    r = price_line(snap.lines[0], snap, RoundingPolicy())
    # VL = (300×1500 + 0.5×350000) × (1 + 2%) = (450000 + 175000) × 1.02 = 637500
    assert r.unit_vl == Decimal("637500")
    # NC = 1.2 × 300000 = 360000
    assert r.unit_nc == Decimal("360000")
    # M = 0.1 × 250000 × 1.05 = 26250
    assert r.unit_m == Decimal("26250")
    assert r.vl == Decimal("6375000") and r.nc == Decimal("3600000") and r.m == Decimal("262500")
    assert r.direct == r.vl + r.nc + r.m
    assert not r.warnings


def test_knc_km_apply_to_amount_not_unit_price(rule_pack, resources, prices):
    snap = make_snapshot(rule_pack, resources, prices, lines=[make_line(k_nc="1.3", k_m="1.09")])
    r = price_line(snap.lines[0], snap, RoundingPolicy())
    assert r.unit_nc == Decimal("360000")
    assert r.nc == Decimal("4680000")  # 10 × 360000 × 1.3
    assert r.m == Decimal("286125")  # 10 × 26250 × 1.09


def test_missing_price_warns_and_does_not_zero_other_components(rule_pack, resources, prices):
    prices = dict(prices)
    del prices["VL.CAT"]
    snap = make_snapshot(rule_pack, resources, prices)
    r = price_line(snap.lines[0], snap, RoundingPolicy())
    codes = {w.code for w in r.warnings}
    assert "MISSING_PRICE" in codes
    assert r.unit_vl == Decimal("459000")  # 300×1500×1.02 — cát bị thiếu giá, không thành 0 toàn dòng
    comp = next(c for c in r.breakdown["components"] if c.get("resource_code") == "VL.CAT")
    assert comp["price"] is None


def test_pending_price_and_unknown_resource_warn(rule_pack, resources, prices):
    prices = dict(prices)
    prices["VL.XM"] = PriceInput(Decimal("1500"), "override:test", status="pending")
    line = make_line(
        components=[NormLine("VL.XM", "MATERIAL", Decimal("1")), NormLine("VL.NOPE", "MATERIAL", Decimal("1"))]
    )
    snap = make_snapshot(rule_pack, resources, prices, lines=[line])
    r = price_line(line, snap, RoundingPolicy())
    codes = {w.code for w in r.warnings}
    assert {"PRICE_NOT_APPROVED", "RESOURCE_NOT_FOUND", "MISSING_PRICE"} <= codes


def test_unit_mismatch_and_unknown_work_item_warn(rule_pack, resources, prices):
    line = make_line(work_item_found=False, work_item_unit="100m3")
    snap = make_snapshot(rule_pack, resources, prices, lines=[line])
    r = price_line(line, snap, RoundingPolicy())
    codes = {w.code for w in r.warnings}
    assert {"WORK_ITEM_NOT_FOUND", "UNIT_MISMATCH"} <= codes


def test_resource_totals_sum_consumption(rule_pack, resources, prices):
    snap = make_snapshot(rule_pack, resources, prices, lines=[make_line("L1", "10"), make_line("L2", "2.5")])
    res = run(snap)
    xm = next(t for t in res.resource_totals if t["resource_code"] == "VL.XM")
    assert Decimal(xm["quantity"]) == Decimal("3750.0000")  # (10 + 2.5) × 300
    assert Decimal(xm["amount"]) == Decimal("5625000")
