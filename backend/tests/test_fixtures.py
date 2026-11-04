import json
from decimal import Decimal
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_rule_pack_tables_are_complete():
    rp = json.loads((FIXTURES / "rule_pack_tt36_2026.json").read_text(encoding="utf-8"))
    od = rp["overhead_direct"]
    assert len(od["thresholds_bn"]) == 7
    for row, vals in od["rows"].items():
        assert len(vals) == 8, row
        assert [Decimal(v) for v in vals] == sorted((Decimal(v) for v in vals), reverse=True), row
    assert len(rp["overhead_labor"]["thresholds_bn"]) == 3
    for vals in rp["overhead_labor"]["rows"].values():
        assert len(vals) == 4
    for vals in rp["temp_housing"]["rows"].values():
        assert len(vals) == 5
    for ct in od["rows"]:
        assert ct in rp["unquantified_work"]["rows"] and ct in rp["taxable_income"]["rows"]
    assert Decimal(rp["vat_rate"]) == Decimal("0.10")
    assert rp["source"]["needs_review_errata"] is True


def test_sample_catalog_is_valid():
    data = json.loads((FIXTURES / "sample_catalog.json").read_text(encoding="utf-8"))
    assert data["release"]["is_sample"] is True
    res_codes = [r["code"] for r in data["resources"]]
    assert len(res_codes) == len(set(res_codes)), "trùng mã nguồn lực"
    wi_codes = [w["code"] for w in data["work_items"]]
    assert len(wi_codes) == len(set(wi_codes)), "trùng mã công tác"
    for r in data["resources"]:
        assert r["unit"], r["code"]
    for w in data["work_items"]:
        assert w["unit"], w["code"]
        for c in w["components"]:
            assert Decimal(c["quantity"]) >= 0
            if not c.get("is_other_pct"):
                assert c["resource"] in res_codes, (w["code"], c["resource"])
    priced = {p["resource"] for p in data["prices"]}
    assert priced == set(res_codes), "mọi nguồn lực mẫu phải có giá mẫu"
