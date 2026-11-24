"""Nhập BoQ từ Excel bất kỳ: đọc file, gợi ý mã, quy đổi đơn vị, ghi vào dự toán và tính."""

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.boqimport import matcher
from apps.boqimport.models import BoqMatchMemory
from apps.boqimport.parser import BoqParseError, parse_number, parse_workbook
from apps.boqimport.units import conversion_factor, parse_unit
from apps.catalog.models import WorkItem
from apps.projects.models import EstimateLine

pytestmark = pytest.mark.django_db


def _xlsx(rows, title_rows=2, sheet="BoQ") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for i in range(title_rows):
        ws.cell(row=i + 1, column=1, value=f"Tiêu đề {i + 1}")
    for r, row in enumerate(rows, title_rows + 2):  # chừa một dòng trống
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


DESIGNER_BOQ = [
    ["STT", "Nội dung công việc", "Đơn vị", "Khối lượng", "Ghi chú"],
    ["(1)", "(2)", "(3)", "(4)", "(5)"],
    ["A", "PHẦN MÓNG", None, None],
    [1, "Đào móng cột bằng thủ công, đất cấp II", "m3", 12.5],
    [2, "Bê tông lót móng đá 4x6 M100", "m3", None],
    [None, "Móng M1: 12 x 1,2 x 0,1", None, 1.44],
    [None, "Móng M2: 18 x 1,2 x 0,1", None, 2.16],
    [3, "Cốt thép móng đường kính ≤10mm", "kg", "820"],
    [4, "Ván khuôn gỗ móng", "m2", "33,6"],
    ["B", "PHẦN HOÀN THIỆN", None, None],
    [5, "Trát tường trong dày 1,5cm vữa XM M75", "m2", 420],
    [6, "Lắp dựng vách kính cường lực khung nhôm Xingfa", "m2", 24],
    [None, "Tổng cộng", None, None],
]


# ----------------------------------------------------------------------------- đơn vị / số


@pytest.mark.parametrize(
    "boq,norm,factor",
    [
        ("m3", "100m3 đất nguyên thổ", Decimal("0.01")),
        ("m³", "1m3", Decimal(1)),
        ("kg", "1 tấn", Decimal("0.001")),
        ("tấn", "1tấn", Decimal(1)),
        ("m2", "100m2", Decimal("0.01")),
        ("m", "100m", Decimal("0.01")),
        ("bộ", "bộ", Decimal(1)),
        ("m2", "1m3", None),
    ],
)
def test_conversion_factor(boq, norm, factor):
    assert conversion_factor(boq, norm) == factor


def test_parse_unit_and_number():
    assert parse_unit("100m3 đá nguyên khai") == parse_unit("100 m3")
    assert parse_number("12,5") == Decimal("12.5")
    assert parse_number("1.234,5") == Decimal("1234.5")
    assert parse_number("1,234,567") == Decimal("1234567")
    assert parse_number("abc") is None


# ----------------------------------------------------------------------------- đọc file


def test_parse_designer_boq_detects_columns_items_and_details():
    p = parse_workbook(_xlsx(DESIGNER_BOQ))
    assert p.header_row == 4
    assert p.columns["name"] == 2 and p.columns["unit"] == 3 and p.columns["qty"] == 4
    assert [it.name for it in p.items] == ["PHẦN MÓNG", "PHẦN HOÀN THIỆN"]
    lot = p.items[0].lines[1]
    assert lot.quantity == Decimal("3.60")  # dòng chính trống → tổng diễn giải
    assert len(lot.details) == 2
    assert p.items[0].lines[3].quantity == Decimal("33.6")
    assert any(s["reason"] == "Dòng tổng cộng" for s in p.skipped)


def test_parse_two_level_header_and_mismatched_details():
    rows = [
        ["TT", "Mã hiệu", "Tên công tác", "ĐVT", "Khối lượng", None],
        [None, None, None, None, "Một cấu kiện", "Toàn bộ"],
        [1, "AF.61111", "Cốt thép móng", "tấn", 0.1, 1.2],
        [None, None, "Móng M1", None, None, 0.5],  # tổng diễn giải 0,5 ≠ 1,2 → bỏ diễn giải
    ]
    p = parse_workbook(_xlsx(rows))
    assert p.columns["code"] == 2
    assert p.columns["qty"] == 6  # "Khối lượng Toàn bộ" ưu tiên hơn "Một cấu kiện"
    ln = p.items[0].lines[0]
    assert ln.quantity == Decimal("1.2") and ln.details == []
    assert any("khác khối lượng" in w for w in ln.warnings)


def test_parse_item_column_and_codes_in_file():
    rows = [
        ["STT", "Hạng mục", "Mã hiệu định mức", "Tên công tác", "Đơn vị", "Khối lượng"],
        [1, "Phần móng", "AF.61111", "Cốt thép móng", "tấn", 1.2],
        [2, "Phần thân", None, "Trát tường trong", "m2", 50],
        [3, "Phần móng", None, "Ván khuôn gỗ móng", "m2", 20],
    ]
    p = parse_workbook(_xlsx(rows))
    assert p.columns["item"] == 2 and p.columns["code"] == 3
    assert [(it.name, len(it.lines)) for it in p.items] == [("Phần móng", 2), ("Phần thân", 1)]
    assert p.items[0].lines[0].code == "AF.61111"


def test_parse_rejects_non_boq_and_xls():
    with pytest.raises(BoqParseError):
        parse_workbook(_xlsx([["Họ tên", "Tuổi"], ["A", 1]]))
    with pytest.raises(BoqParseError, match="xlsx"):
        parse_workbook(b"\xd0\xcf\x11\xe0 old xls")


def test_manual_column_override():
    rows = [["A", "B", "C"], ["Đào móng cột bằng thủ công, đất cấp II", "m3", 5]]
    with pytest.raises(BoqParseError):
        parse_workbook(_xlsx(rows))
    p = parse_workbook(_xlsx(rows), header_row=4, columns={"name": 1, "unit": 2, "qty": 3})
    assert p.items[0].lines[0].quantity == 5


# ----------------------------------------------------------------------------- gợi ý mã


def test_matcher_uses_dimensions_and_units(seeded):
    idx = matcher.get_index(seeded["norm"].id)
    c = matcher.suggest(idx, "Cốt thép móng d≤10mm", "kg")
    assert c[0].code == "AF.61111" and c[0].factor == Decimal("0.001")
    c = matcher.suggest(idx, "Cốt thép móng phi 16", "tấn")
    assert c[0].code == "AF.61121"  # 16mm vi phạm ≤10 → mã ≤18
    c = matcher.suggest(idx, "Trát tường ngoài dày 1,5cm", "m2")
    assert c[0].code == "AK.21211"
    assert matcher.confidence(matcher.suggest(idx, "Lắp đặt thang máy tải khách", "bộ")) == "low"


# ----------------------------------------------------------------------------- API


def _revision(client, seeded):
    p = client.post(
        "/api/v1/projects",
        {
            "name": "Nhập BoQ",
            "region": "Hà Nội",
            "price_period": "2026-Q3",
            "construction_type": "CIVIL",
            "rule_pack": seeded["pack"].id,
            "norm_release": seeded["norm"].id,
            "price_release": seeded["price"].id,
        },
        format="json",
    )
    rev = client.post(f"/api/v1/projects/{p.data['id']}/revisions", {"title": "Lần 1"}, format="json")
    rid = rev.data["id"]
    client.post(f"/api/v1/revisions/{rid}/items", {"name": "Hạng mục 1", "order": 1}, format="json")
    return rid


def _upload(client, rid, data: bytes, **extra):
    f = BytesIO(data)
    f.name = "boq.xlsx"
    return client.post(f"/api/v1/revisions/{rid}/boq-import/preview", {"file": f, **extra}, format="multipart")


def _accept_all(preview):
    return {
        "filename": "boq.xlsx",
        "items": [
            {
                "name": it["name"],
                "lines": [
                    {
                        "row": ln["row"],
                        "name": ln["name"],
                        "unit": ln["unit"],
                        "quantity": ln["quantity"],
                        "details": ln["details"],
                        "work_item": ln["selected"]["work_item"] if ln["selected"] else None,
                        "kind": ln.get("kind", "work"),
                    }
                    for ln in it["lines"]
                ],
            }
            for it in preview["items"]
        ],
    }


def test_preview_then_commit_calculates(client, seeded):
    rid = _revision(client, seeded)
    r = _upload(client, rid, _xlsx(DESIGNER_BOQ))
    assert r.status_code == 200, r.content
    lines = {ln["name"]: ln for it in r.data["items"] for ln in it["lines"]}
    assert lines["Cốt thép móng đường kính ≤10mm"]["selected"]["code"] == "AF.61111"
    assert lines["Ván khuôn gỗ móng"]["selected"]["factor"] == "0.01"
    assert lines["Lắp dựng vách kính cường lực khung nhôm Xingfa"]["selected"] is None  # không có mã phù hợp

    c = client.post(f"/api/v1/revisions/{rid}/boq-import/commit", _accept_all(r.data), format="json")
    assert c.status_code == 201, c.content
    assert c.data["lines_created"] == 6 and c.data["custom"] == 1 and c.data["default_items_removed"] == 1
    assert c.data["run"]["status"] == "done"

    rev = client.get(f"/api/v1/revisions/{rid}").data
    assert [it["name"] for it in rev["items"]] == ["PHẦN MÓNG", "PHẦN HOÀN THIỆN"]
    thep = EstimateLine.objects.get(item__revision_id=rid, work_item__code="AF.61111")
    assert thep.quantity == Decimal("0.82") and thep.quantity_expr == "820/1000" and thep.unit == "tấn"
    assert "820 kg" in thep.note
    lot = EstimateLine.objects.get(item__revision_id=rid, work_item__code="AF.11111")
    assert lot.quantity == Decimal("3.6") and len(lot.details) == 2
    custom = EstimateLine.objects.get(item__revision_id=rid, work_item__isnull=True)
    assert custom.custom_code == "TT.01" and custom.quantity == 24

    # lần nhập sau: lựa chọn đã được ghi nhớ
    assert BoqMatchMemory.objects.filter(work_item__code="AF.61111").exists()
    r2 = _upload(client, rid, _xlsx(DESIGNER_BOQ))
    again = {ln["name"]: ln for it in r2.data["items"] for ln in it["lines"]}
    assert again["Cốt thép móng đường kính ≤10mm"]["source"] == "memory"


def test_commit_rejects_incompatible_unit_without_factor(client, seeded):
    rid = _revision(client, seeded)
    wi = WorkItem.objects.get(code="AF.12111")  # m3
    payload = {
        "items": [
            {"name": "X", "lines": [{"name": "Bê tông móng", "unit": "m2", "quantity": "10", "work_item": wi.id}]}
        ]
    }
    r = client.post(f"/api/v1/revisions/{rid}/boq-import/commit", payload, format="json")
    assert r.status_code == 400 and "quy đổi" in r.data["detail"]
    assert not EstimateLine.objects.filter(item__revision_id=rid).exists()
    payload["items"][0]["lines"][0]["factor"] = "0.2"
    r = client.post(f"/api/v1/revisions/{rid}/boq-import/commit", payload, format="json")
    assert r.status_code == 201, r.content
    assert EstimateLine.objects.get(item__revision_id=rid).quantity == Decimal("2")


def test_preview_bad_file(client, seeded):
    rid = _revision(client, seeded)
    r = _upload(client, rid, b"not excel")
    assert r.status_code == 400 and "xlsx" in r.data["detail"]


# ----------------------------------------------------------------------------- dấu tiếng Việt, loại dòng


def test_router_not_matched_by_dinh_muc(seeded):
    from apps.catalog.models import WorkItem as WI

    WI.objects.create(release=seeded["norm"], code="BB.85201", name="Lắp đồng hồ đo áp lực, Định mức", unit="cái")
    idx = matcher.get_index(seeded["norm"].id)
    assert matcher.confidence(matcher.suggest_best(idx, "Bộ định tuyến Router", "Bộ", "equipment")) == "low"


def test_accents_distinguish_cap_cat(seeded):
    from apps.catalog.models import WorkItem as WI

    rel = seeded["norm"]
    WI.objects.create(release=rel, code="CH.11210", name="Đo vẽ mặt cắt ngang, Cấp địa hình I", unit="100m")
    WI.objects.create(release=rel, code="BB.99001", name="Kéo rải cáp mạng Cat6 trong ống", unit="100m")
    idx = matcher.get_index(rel.id)
    c = matcher.suggest_best(idx, "Cáp Cat6", "m")
    assert c[0].code == "BB.99001"
    assert all(x.code != "CH.11210" for x in c)
    assert "cáp" in matcher.features("Cáp Cat6") and "cáp" not in matcher.features("cấp địa hình")
    # BoQ gõ không dấu vẫn tìm được
    assert matcher.suggest_best(idx, "Trat tuong ngoai day 1,5cm", "m2")[0].code == "AK.21211"


@pytest.mark.parametrize(
    "name,unit,kind",
    [
        ("Loa âm trần", "Cái", "equipment"),
        ("Tủ RACK 32U", "Bộ", "equipment"),
        ("Lắp đặt camera IP dome", "cái", "work"),
        ("Cáp Cat6", "m", "work"),
        ("Vận hành, chạy thử", "Gói", "lump"),
        ("Dây nhảy Cat6 UTP dài 1M", "Chiếc", "equipment"),
        ("Bộ định tuyến Router", "Bộ", "equipment"),
        ("Bê tông móng", "m3", "work"),
    ],
)
def test_line_kind(name, unit, kind):
    assert matcher.line_kind(name, unit) == kind


def test_parse_repeated_header_and_heading_in_other_column():
    rows = [
        ["STT", "Tên thiết bị / vật tư", "ĐVT", "Khối lượng"],
        ["I. HỆ THỐNG CAMERA", None, None, None],  # tiêu đề nằm ở cột STT
        [1, "Camera IP dome", "Cái", 10],
        ["STT", "Tên thiết bị / vật tư", "ĐVT", "Khối lượng"],  # tiêu đề lặp lại
        ["II", "HỆ THỐNG MẠNG", None, None],
        [1, "Cáp Cat6", "m", 1200],
    ]
    p = parse_workbook(_xlsx(rows))
    assert [it.name for it in p.items] == ["HỆ THỐNG CAMERA", "HỆ THỐNG MẠNG"]
    assert sum(len(it.lines) for it in p.items) == 2
    assert any(s["reason"] == "Dòng tiêu đề lặp lại" for s in p.skipped)


def test_equipment_goes_to_equipment_cost_with_install_line(client, seeded):
    from apps.projects.models import EquipmentCost

    rid = _revision(client, seeded)
    rows = [
        ["STT", "Tên thiết bị / vật tư", "ĐVT", "Khối lượng"],
        ["A", "HỆ THỐNG CAMERA", None, None],
        [1, "Camera IP dome 2MP", "Cái", 10],
        [2, "Đầu ghi hình NVR 32 kênh", "Cái", 1],
        ["B", "THIẾT BỊ KHÁC", None, None],
        [3, "Máy chủ lưu trữ", "Bộ", 1],
    ]
    r = _upload(client, rid, _xlsx(rows))
    lines = {ln["name"]: ln for it in r.data["items"] for ln in it["lines"]}
    cam = lines["Camera IP dome 2MP"]
    assert cam["kind"] == "equipment" and cam["selected"]["code"] == "BB.31111"
    payload = _accept_all(r.data)
    for it in payload["items"]:
        for ln in it["lines"]:
            ln["kind"] = "equipment"
            if ln["name"].startswith("Camera"):
                ln["unit_price"] = "2500000"
            elif ln["name"].startswith("Đầu ghi"):
                ln["work_item"] = None
    c = client.post(f"/api/v1/revisions/{rid}/boq-import/commit", payload, format="json")
    assert c.status_code == 201, c.content
    assert c.data["equipment"] == 3 and c.data["equipment_unpriced"] == 2
    eq = {e.name: e for e in EquipmentCost.objects.filter(revision_id=rid)}
    assert eq["Camera IP dome 2MP [HỆ THỐNG CAMERA]"].unit_price == 2500000
    inst = EstimateLine.objects.filter(item__revision_id=rid)
    assert [ln.work_item.code for ln in inst] == ["BB.31111"] * (
        1 + int(lines["Máy chủ lưu trữ"]["selected"] is not None)
    )
    assert "(cho: Camera IP dome 2MP)" in inst[0].name and inst[0].quantity == 10
    # Camera là vật liệu trong định mức lắp camera → giá 0 (đã ở Chi phí thiết bị), không tính hai lần
    from apps.projects.models import ResourceOverride

    assert c.data["equipment_in_norm"] == ["Camera IP dome 2MP"]
    assert ResourceOverride.objects.get(revision_id=rid, resource__code="VL.CAMERA").price == 0
    # hạng mục chỉ có thiết bị không lắp đặt → không tạo hạng mục rỗng
    rev = client.get(f"/api/v1/revisions/{rid}").data
    assert all(it["lines"] for it in rev["items"])


def test_auto_apply_catalog_prices(client, seeded):
    from apps.catalog.models import DatasetRelease
    from apps.datasync.models import PriceCatalogItem
    from apps.pricebook.models import PriceObservation
    from apps.projects.models import ResourceOverride

    PriceObservation.objects.filter(resource__code__in=["VL.XM", "VL.CAT.V"]).delete()
    cat = DatasetRelease.objects.create(
        kind="CATALOG",
        name="Công bố giá HN",
        version="q3",
        region="Hà Nội",
        status="published",
        meta={"period": "2026-Q3"},
    )
    # Xi măng: 2 dòng trùng tên, khác nhóm → chọn nhóm "Xây dựng" (định mức chương A); công bố theo tấn → quy về kg
    PriceCatalogItem.objects.create(release=cat, name="Xây dựng | Xi măng PC40", unit="tấn", price=1700000, page=3)
    PriceCatalogItem.objects.create(release=cat, name="Sửa chữa | Xi măng PC40", unit="tấn", price=1900000, page=9)
    # Cát vàng: 2 giá cùng nhóm → không tự áp
    PriceCatalogItem.objects.create(release=cat, name="Cát vàng", unit="m3", price=400000, page=4)
    PriceCatalogItem.objects.create(release=cat, name="Cát vàng", unit="m3", price=450000, page=5)

    rid = _revision(client, seeded)
    item = client.get(f"/api/v1/revisions/{rid}").data["items"][0]["id"]
    client.post(
        f"/api/v1/revisions/{rid}/lines",
        {"item": item, "work_item": WorkItem.objects.get(code="AF.11111").id, "quantity": "2"},
        format="json",
    )
    r = client.post(f"/api/v1/revisions/{rid}/auto-prices")
    assert r.status_code == 200, r.content
    assert [a["code"] for a in r.data["applied"]] == ["VL.XM"]
    assert r.data["applied"][0]["price"] == "1700"
    assert [a["code"] for a in r.data["ambiguous"]] == ["VL.CAT.V"]
    ov = ResourceOverride.objects.get(revision_id=rid, resource__code="VL.XM")
    assert "Tự áp từ công bố giá" in ov.reason and "tr.3" in ov.reason
    assert [w for w in r.data["run"]["warnings"] if w.get("resource_code") == "VL.XM"] == []
    # chạy lại không áp trùng
    r2 = client.post(f"/api/v1/revisions/{rid}/auto-prices")
    assert r2.data["applied"] == []
