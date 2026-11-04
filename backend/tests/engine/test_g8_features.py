"""Diễn giải khối lượng nhiều dòng, đơn giá tạm tính, tổng hợp theo hạng mục, đọc số bằng chữ."""

from decimal import Decimal

import pytest

from apps.calculation.engine import run
from apps.calculation.engine.core import price_line
from apps.calculation.engine.quantity import QuantityError, detail_value, sum_details
from apps.calculation.engine.rounding import RoundingPolicy
from apps.reports.vnwords import vnd_in_words

from .conftest import make_line, make_snapshot


def test_detail_rows_note_formula_and_dimensions():
    total, rows = sum_details(
        [
            {"text": "Móng trục A:"},  # ghi chú → không cộng
            {"text": "Móng M1", "expr": "1.2*1.8*0.85", "n": "4"},  # 4 × 1,836
            {"text": "Giằng", "l": "12,5", "w": "0.22", "h": "0.3"},  # D×R×C
            {"text": "Trừ lỗ", "expr": "-0.5"},
        ]
    )
    assert rows[0]["value"] is None
    assert Decimal(rows[1]["value"]) == Decimal("7.344")
    assert Decimal(rows[2]["value"]) == Decimal("0.825")
    assert total == Decimal("7.344") + Decimal("0.825") - Decimal("0.5")
    assert rows[2]["l"] == "12.5"


def test_detail_bad_formula_reports_row():
    with pytest.raises(QuantityError, match="Dòng diễn giải 2"):
        sum_details([{"text": "ok", "expr": "1"}, {"expr": "__import__('os')"}])
    assert detail_value({"text": "chỉ ghi chú"}) is None


def test_manual_unit_price_for_custom_line(rule_pack, resources, prices):
    line = make_line(components=[], manual_vl=Decimal("120000"), manual_nc=Decimal("45000"))
    snap = make_snapshot(rule_pack, resources, prices, lines=[line])
    r = price_line(line, snap, RoundingPolicy())
    assert (r.unit_vl, r.unit_nc, r.unit_m) == (Decimal("120000"), Decimal("45000"), Decimal("0"))
    assert r.direct == Decimal("1650000")
    codes = {w.code for w in r.warnings}
    assert "MANUAL_UNIT_PRICE" in codes and "NO_NORM" not in codes


def test_custom_line_without_price_still_warns(rule_pack, resources, prices):
    line = make_line(components=[])
    r = price_line(line, make_snapshot(rule_pack, resources, prices, lines=[line]), RoundingPolicy())
    assert r.direct == 0 and "NO_NORM" in {w.code for w in r.warnings}


def test_item_summaries_split_by_item(rule_pack, resources, prices):
    a = make_line("L1", quantity="10")
    b = make_line("L2", quantity="5")
    b.item_id, b.item_name = "I2", "HM2"
    res = run(make_snapshot(rule_pack, resources, prices, lines=[a, b], approved_construction_cost_bn=Decimal("10")))
    items = {it["item_id"]: it for it in res.summary["items"]}
    assert set(items) == {"I1", "I2"}
    t_sum = sum(Decimal(it["values"]["T"]) for it in items.values())
    assert t_sum == Decimal(res.summary["values"]["T"])
    g_sum = sum(Decimal(it["values"]["GXD"]) for it in items.values())
    assert abs(g_sum - Decimal(res.summary["values"]["GXD"])) <= 5  # chỉ lệch do làm tròn


@pytest.mark.parametrize(
    "n,words",
    [
        (0, "Không đồng"),
        (15, "Mười lăm đồng"),
        (21, "Hai mươi mốt đồng"),
        (105, "Một trăm linh năm đồng"),
        (1005, "Một nghìn không trăm linh năm đồng"),
        (56016761, "Năm mươi sáu triệu không trăm mười sáu nghìn bảy trăm sáu mươi mốt đồng"),
        (3000000000, "Ba tỷ đồng"),
    ],
)
def test_vnd_in_words(n, words):
    assert vnd_in_words(n) == words
