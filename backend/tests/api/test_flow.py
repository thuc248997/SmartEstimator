"""End-to-end: project → revision → items/lines → calculate → explain → approve → export → re-read xlsx."""

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from apps.calculation.models import CalculationRun
from apps.catalog.models import WorkItem

pytestmark = pytest.mark.django_db


def _project_payload(seeded, **over):
    d = {
        "name": "Nhà làm việc 3 tầng (mẫu)",
        "region": "Hà Nội",
        "price_period": "2026-Q3",
        "construction_type": "CIVIL",
        "rule_pack": seeded["pack"].id,
        "norm_release": seeded["norm"].id,
        "price_release": seeded["price"].id,
        "approved_construction_cost_bn": "12",
    }
    d.update(over)
    return d


def _setup_revision(client, seeded, lines_spec):
    p = client.post("/api/v1/projects", _project_payload(seeded), format="json")
    assert p.status_code == 201, p.content
    rev = client.post(f"/api/v1/projects/{p.data['id']}/revisions", {"title": "Dự toán lần 1"}, format="json")
    assert rev.status_code == 201
    rid = rev.data["id"]
    item = client.post(f"/api/v1/revisions/{rid}/items", {"name": "Phần thô", "order": 1}, format="json")
    assert item.status_code == 201
    payload = []
    for i, (code, expr, qty) in enumerate(lines_spec, 1):
        wi = WorkItem.objects.get(code=code)
        payload.append(
            {"item": item.data["id"], "order": i, "work_item": wi.id, "quantity_expr": expr, "quantity": qty}
        )
    r = client.post(f"/api/v1/revisions/{rid}/lines", payload, format="json")
    assert r.status_code == 201, r.content
    return p.data["id"], rid, item.data["id"], r.data


def test_full_flow(client, seeded):
    pid, rid, iid, lines = _setup_revision(
        client, seeded, [("AF.12111", "2*(3.5+4.2)*0.22", "0"), ("AE.22211", "", "15.5"), ("BB.31111", "", "4")]
    )
    # ---- calculate (sync, < limit)
    calc = client.post(f"/api/v1/revisions/{rid}/calculate")
    assert calc.status_code == 200, calc.content
    assert calc.data["status"] == "done"
    run_id = calc.data["id"]
    values = {k: Decimal(v) for k, v in calc.data["result"]["summary"]["values"].items()}
    assert values["T"] > 0 and values["GXDTT"] > values["T"]
    assert values["GT"] == values["C"] + values["TT"]
    assert values["GXD"] == values["GXDTT"] + values["GTGT"]
    codes = {w["code"] for w in calc.data["warnings"]}
    assert "MISSING_PRICE" not in codes and "RULE_PACK_NOT_APPROVED" in codes

    # ---- per-line result + explain
    detail = client.get(f"/api/v1/calculation-runs/{run_id}")
    assert detail.status_code == 200 and len(detail.data["lines"]) == 3
    l0 = detail.data["lines"][0]
    assert Decimal(l0["quantity"]) == Decimal("3.388")  # công thức KL đã tính
    ex = client.get(f"/api/v1/calculation-runs/{run_id}/explain", {"line_id": lines[0]["id"]})
    assert ex.status_code == 200
    comp_codes = {c.get("resource_code") for c in ex.data["breakdown"]["components"]}
    assert "VL.XM" in comp_codes and ex.data["breakdown"]["formulas"]["unit_vl"].startswith("Σ")
    xm = next(c for c in ex.data["breakdown"]["components"] if c.get("resource_code") == "VL.XM")
    assert xm["price_source"].startswith("release:")

    # ---- override price → recalculation changes only affected line
    ov = client.post(
        f"/api/v1/revisions/{rid}/overrides",
        {"resource": _res_id("VL.XM"), "price": "1700", "reason": "Báo giá NCC 10/2026"},
        format="json",
    )
    assert ov.status_code == 201
    calc2 = client.post(f"/api/v1/revisions/{rid}/calculate").data
    assert calc2["output_hash"] != calc.data["output_hash"]
    d2 = client.get(f"/api/v1/calculation-runs/{calc2['id']}").data
    assert d2["lines"][0]["vl"] != l0["vl"]
    assert d2["lines"][2]["vl"] == detail.data["lines"][2]["vl"]  # camera không dùng xi măng
    ex2 = client.get(f"/api/v1/calculation-runs/{calc2['id']}/explain", {"line_id": lines[0]["id"]}).data
    assert next(c for c in ex2["breakdown"]["components"] if c.get("resource_code") == "VL.XM")[
        "price_source"
    ].startswith("override:")

    # ---- optimistic concurrency
    patch = client.patch(
        f"/api/v1/revisions/{rid}/lines/{lines[1]['id']}", {"quantity": "16", "version": 99}, format="json"
    )
    assert patch.status_code == 409
    patch = client.patch(
        f"/api/v1/revisions/{rid}/lines/{lines[1]['id']}", {"quantity": "16", "version": 1}, format="json"
    )
    assert patch.status_code == 200 and patch.data["version"] == 2

    # ---- approve locks; re-calculation of locked revision reproduces the same hash
    calc3 = client.post(f"/api/v1/revisions/{rid}/calculate").data
    ap = client.post(f"/api/v1/revisions/{rid}/approve", {"reason": "OK"}, format="json")
    assert ap.status_code == 200, ap.content
    assert ap.data["status"] == "approved" and ap.data["content_hash"] == calc3["output_hash"]
    locked = client.patch(
        f"/api/v1/revisions/{rid}/lines/{lines[1]['id']}", {"quantity": "1", "version": 2}, format="json"
    )
    assert locked.status_code == 400
    # thay đổi giá gốc sau khi khóa không được ảnh hưởng
    from apps.pricebook.models import PriceObservation

    PriceObservation.objects.filter(resource__code="VL.CAT.V").update(price=Decimal("999999"))
    calc4 = client.post(f"/api/v1/revisions/{rid}/calculate").data
    assert calc4["output_hash"] == calc3["output_hash"]

    # ---- export xlsx and read it back
    exp = client.post(f"/api/v1/revisions/{rid}/export?template=estimate-xlsx")
    assert exp.status_code == 200, exp.content
    assert exp["Content-Type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(BytesIO(exp.content))
    assert wb.sheetnames == [
        "Bia",
        "ThamSo",
        "TienLuong",
        "PhanTichVatTu",
        "TongHopVatTu",
        "TongHopKinhPhi",
        "THChiPhiXD",
        "ChiPhiThietBi",
    ]
    ws = wb["TongHopKinhPhi"]
    engine_vals = {ws.cell(row=r, column=6).value: ws.cell(row=r, column=5).value for r in range(6, 21)}
    summary3 = CalculationRun.objects.get(pk=calc3["id"]).result["summary"]["values"]
    assert Decimal(str(engine_vals["GXD"])) == Decimal(summary3["GXD"])
    assert ws.cell(row=6 + 5, column=4).value.startswith("=ROUND(")  # dòng C là công thức sống
    tl = wb["TienLuong"]
    formulas = [tl.cell(row=r, column=12).value for r in range(6, 12) if tl.cell(row=r, column=12).value]
    assert all(f.startswith("=") for f in formulas)
    assert wb["ThamSo"]["A3"].value.startswith("DỮ LIỆU MẪU")


def test_missing_price_blocks_approve_unless_forced(client, seeded):
    from apps.pricebook.models import PriceObservation

    PriceObservation.objects.filter(resource__code="VL.CAMERA").delete()
    _, rid, _, lines = _setup_revision(client, seeded, [("BB.31111", "", "2")])
    calc = client.post(f"/api/v1/revisions/{rid}/calculate").data
    assert any(w["code"] == "MISSING_PRICE" for w in calc["warnings"])
    assert Decimal(calc["result"]["summary"]["values"]["VL"]) > 0  # RJ45 vẫn có giá
    ap = client.post(f"/api/v1/revisions/{rid}/approve", {}, format="json")
    assert ap.status_code == 409
    ap = client.post(f"/api/v1/revisions/{rid}/approve", {"force": True, "reason": "tạm duyệt"}, format="json")
    assert ap.status_code == 200


def test_formula_injection_is_escaped(client, seeded):
    p = client.post("/api/v1/projects", _project_payload(seeded, name='=HYPERLINK("http://x")'), format="json")
    rid = client.post(f"/api/v1/projects/{p.data['id']}/revisions", {}, format="json").data["id"]
    iid = client.post(f"/api/v1/revisions/{rid}/items", {"name": "=1+1"}, format="json").data["id"]
    wi = WorkItem.objects.get(code="AK.84111")
    client.post(
        f"/api/v1/revisions/{rid}/lines",
        {"item": iid, "work_item": wi.id, "quantity": "10", "name": "=CMD()"},
        format="json",
    )
    client.post(f"/api/v1/revisions/{rid}/calculate")
    exp = client.post(f"/api/v1/revisions/{rid}/export")
    tl = load_workbook(BytesIO(exp.content))["TienLuong"]
    texts = [c.value for row in tl.iter_rows(min_row=1, max_row=8) for c in row if isinstance(c.value, str)]
    assert all(not t.startswith("=") or t.startswith(("=ROUND", "=I", "=SUM")) for t in texts)
    assert any(t.startswith("'=") for t in texts)


def test_catalog_search_and_prices(client, seeded):
    r = client.get("/api/v1/catalog/work-items", {"query": "BB.31"})
    assert r.status_code == 200 and r.data["count"] == 2
    wid = r.data["results"][0]["id"]
    n = client.get(f"/api/v1/catalog/work-items/{wid}/norms")
    assert n.status_code == 200 and len(n.data) >= 2
    pr = client.get("/api/v1/prices", {"resource__code": "VL.XM", "region": "Hà Nội", "period": "2026-Q3"})
    assert pr.data["count"] == 1 and Decimal(pr.data["results"][0]["price"]) == Decimal("1650")
    rp = client.get("/api/v1/rule-packs")
    assert rp.data["results"][0]["code"] == "TT36-2026"


def test_unauthenticated_denied(db):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/v1/projects").status_code == 401


def _res_id(code):
    from apps.catalog.models import Resource

    return Resource.objects.get(code=code).id


def test_item_rename_delete_and_breakdown_in_run(client, seeded):
    _, rid, iid, lines = _setup_revision(client, seeded, [("AK.84111", "", "10")])
    r = client.patch(f"/api/v1/revisions/{rid}/items/{iid}", {"name": "Hoàn thiện"}, format="json")
    assert r.status_code == 200 and r.data["name"] == "Hoàn thiện"
    run = client.post(f"/api/v1/revisions/{rid}/calculate").data
    detail = client.get(f"/api/v1/calculation-runs/{run['id']}").data
    assert detail["lines"][0]["breakdown"]["components"]
    assert client.delete(f"/api/v1/revisions/{rid}/items/{iid}").status_code == 204
    assert client.get(f"/api/v1/revisions/{rid}").data["items"] == []


def test_spa_served_at_root(client, settings, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    settings.FRONTEND_DIST = tmp_path
    assert b"id=root" in client.get("/").content


def test_g8_style_details_manual_price_reorder_equipment_export(client, seeded):
    pid, rid, iid, lines = _setup_revision(client, seeded, [("AF.12111", "", "1"), ("AE.22211", "", "2")])
    l1, l2 = lines
    # diễn giải khối lượng nhiều dòng → quantity = Σ
    r = client.patch(
        f"/api/v1/revisions/{rid}/lines/{l1['id']}",
        {
            "version": l1["version"],
            "details": [{"text": "Móng M1", "expr": "1.2*1.8*0.85", "n": "2"}, {"text": "Ghi chú:"}],
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    assert Decimal(r.data["quantity"]) == Decimal("3.672") and r.data["quantity_expr"] == ""
    # sửa khối lượng trực tiếp khi đang có diễn giải → 400
    bad = client.patch(f"/api/v1/revisions/{rid}/lines/{l1['id']}", {"quantity": "9"}, format="json")
    assert bad.status_code == 400
    # mã tạm tính có đơn giá nhập tay
    c = client.post(
        f"/api/v1/revisions/{rid}/lines",
        {
            "item": iid,
            "order": 3,
            "custom_code": "TT.01",
            "name": "Lắp tủ rack",
            "unit": "bộ",
            "quantity": "2",
            "manual_vl": "1500000",
            "manual_nc": "200000",
        },
        format="json",
    )
    assert c.status_code == 201, c.content
    # sắp xếp lại: dòng tạm tính lên đầu
    order = [c.data["id"], l1["id"], l2["id"]]
    ro = client.post(f"/api/v1/revisions/{rid}/items/{iid}/reorder", {"line_ids": order}, format="json")
    assert ro.status_code == 200 and [ln["id"] for ln in ro.data["lines"]] == order
    # chi phí thiết bị
    eq = client.post(
        f"/api/v1/revisions/{rid}/equipment",
        {"name": "Điều hòa 18000BTU", "unit": "bộ", "quantity": "3", "unit_price": "12500000"},
        format="json",
    )
    assert eq.status_code == 201 and eq.data["amount_after_tax"] == "41250000"
    # thông tin công trình
    pr = client.patch(f"/api/v1/projects/{pid}", {"investor": "UBND phường X", "preparer": "Kỹ sư A"}, format="json")
    assert pr.status_code == 200
    run = client.post(f"/api/v1/revisions/{rid}/calculate").data
    assert run["status"] == "done"
    detail = client.get(f"/api/v1/calculation-runs/{run['id']}").data
    tt = next(ln for ln in detail["lines"] if ln["code"] == "TT.01")
    assert Decimal(tt["unit_vl"]) == 1500000 and Decimal(tt["direct"]) == 3400000
    codes = {w["code"] for w in tt["warnings"]}
    assert "CUSTOM_ITEM" in codes and "WORK_ITEM_NOT_FOUND" not in codes  # tạm tính có giá: không chặn duyệt
    assert run["result"]["summary"]["items"][0]["name"] == "Phần thô"
    x = client.post(f"/api/v1/revisions/{rid}/export?template=estimate-xlsx")
    assert x.status_code == 200
    wb = load_workbook(BytesIO(x.content))
    assert wb.sheetnames[0] == "Bia" and {"THChiPhiXD", "ChiPhiThietBi"} <= set(wb.sheetnames)
    tl = wb["TienLuong"]
    texts = [str(c.value) for c in tl["C"] if c.value]
    assert any("Móng M1" in t for t in texts)
    assert any(str(c.value).startswith("=ROUND(SUM(E") for c in tl["E"] if c.value)
    cover = {r[1].value: r[2].value for r in wb["Bia"].iter_rows(min_row=11, max_row=20) if r[1].value}
    assert cover["Chi phí thiết bị (sau thuế)"] == "41.250.000 đồng"
    assert cover["Bằng chữ"].endswith("đồng")
    # sao chép revision mang theo diễn giải + thiết bị
    rev2 = client.post(f"/api/v1/projects/{pid}/revisions", {"copy_from": rid}, format="json").data
    assert rev2["equipment"][0]["name"] == "Điều hòa 18000BTU"
    copied = [ln for it in rev2["items"] for ln in it["lines"] if ln["code"] == "AF.12111"][0]
    assert copied["details"][0]["text"] == "Móng M1"


def test_catalog_multi_keyword_and_groups(client, seeded):
    r = client.get("/api/v1/catalog/work-items", {"query": "trát,ngoài", "release": seeded["norm"].id})
    assert [w["code"] for w in r.data["results"]] == ["AK.21211"]
    r = client.get("/api/v1/catalog/work-items", {"query": "AF", "page_size": 200})
    assert r.data["count"] == len(r.data["results"]) >= 13
    g = client.get("/api/v1/catalog/work-items/groups", {"release": seeded["norm"].id}).data
    assert {"code": "AF", "name": "Công tác bê tông tại chỗ, cốt thép, ván khuôn", "count": 13} in g


def test_equipment_defaults_and_validation(client, seeded):
    _, rid, _, _ = _setup_revision(client, seeded, [("AF.12111", "", "1")])
    r = client.post(f"/api/v1/revisions/{rid}/equipment", {"name": "Máy phát điện"}, format="json")
    assert r.status_code == 201, r.content
    assert r.data["amount"] == "0" and r.data["amount_after_tax"] == "0"
    bad = client.patch(f"/api/v1/revisions/{rid}/equipment/{r.data['id']}", {"vat_rate": "10"}, format="json")
    assert bad.status_code == 400
    # PATCH chỉ ghi trường được gửi (không ghi đè số lượng bằng bản cũ)
    from apps.projects.models import EquipmentCost

    eq = EquipmentCost.objects.get(pk=r.data["id"])
    EquipmentCost.objects.filter(pk=eq.pk).update(quantity=6)
    ok = client.patch(f"/api/v1/revisions/{rid}/equipment/{eq.pk}", {"unit_price": "100"}, format="json")
    assert ok.data["quantity"] == "6.000" and ok.data["amount"] == "600"
