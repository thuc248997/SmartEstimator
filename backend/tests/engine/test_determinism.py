from decimal import Decimal

from apps.calculation.engine import Snapshot, run
from apps.calculation.engine.snapshot import PriceInput

from .conftest import make_line, make_snapshot


def test_same_snapshot_same_hash(rule_pack, resources, prices):
    s1 = make_snapshot(rule_pack, resources, prices, lines=[make_line("L1"), make_line("L2", "3")])
    s2 = Snapshot.from_json(s1.to_json())  # round-trip qua JSON như khi lưu snapshot vào DB
    r1, r2 = run(s1), run(s2)
    assert r1.input_hash == r2.input_hash
    assert r1.output_hash == r2.output_hash
    assert r1.to_json() == r2.to_json()


def test_price_change_only_touches_affected_lines(rule_pack, resources, prices):
    base = make_snapshot(rule_pack, resources, prices, lines=[make_line("L1"), make_line("L2", "3", components=[])])
    r1 = run(base)
    prices2 = dict(prices)
    prices2["VL.XM"] = PriceInput(Decimal("1600"), "override:báo giá mới")
    r2 = run(make_snapshot(rule_pack, resources, prices2, lines=base.lines))
    assert r1.output_hash != r2.output_hash
    assert r1.lines[0].vl != r2.lines[0].vl
    assert r1.lines[1].to_json() == r2.lines[1].to_json()


def test_line_order_independent_of_input_order(rule_pack, resources, prices):
    a = make_line("L1")
    b = make_line("L2", "3")
    b.order = 2
    r1 = run(make_snapshot(rule_pack, resources, prices, lines=[a, b]))
    r2 = run(make_snapshot(rule_pack, resources, prices, lines=[b, a]))
    assert r1.output_hash == r2.output_hash
