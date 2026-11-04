"""Excel export (openpyxl) with live formulas for the 4 P0 tables.

Sheets: ThamSo (tham số/tỷ lệ), TienLuong, PhanTichVatTu, TongHopVatTu, TongHopKinhPhi.
All cell values derived from the persisted CalculationRun (never recomputed here); formulas let a
reviewer re-check the arithmetic in Excel. Values starting with = + - @ are escaped (formula injection).
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.calculation.models import CalculationRun

from .vnwords import vnd_in_words

TEMPLATE_VERSION = "estimate-xlsx/0.2"
_THIN = Side(style="thin", color="999999")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
BOLD = Font(bold=True)
VND = "#,##0"
QTY = "#,##0.000"
CONS = "#,##0.0000"


def safe(v):
    """Escape cell text so it is never interpreted as a formula."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def num(v) -> float | int | None:
    if v is None:
        return None
    d = Decimal(str(v))
    return int(d) if d == d.to_integral_value() else float(d)


def _header(ws, row: int, titles: list[str], widths: list[int] | None = None):
    for i, t in enumerate(titles, 1):
        c = ws.cell(row=row, column=i, value=t)
        c.font = BOLD
        c.fill = HEAD_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w


def _title(ws, text: str, project: str, sub: str = ""):
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Công trình: {project}"
    if sub:
        ws["A3"] = sub


DETAIL_FONT = Font(italic=True, color="555555")
STATUS_VI = {"draft": "bản nháp", "review": "đang thẩm định", "approved": "đã phê duyệt", "issued": "đã phát hành"}


def _fmt_num(v: str | None) -> str:
    if v is None:
        return ""
    d = Decimal(str(v)).normalize()
    return format(d, "f").replace(".", ",")


def _detail_text(d: dict) -> str:
    """'- Móng M1: 1,2*1,8*0,85' hoặc '- Tường trục A: 2 x 12 x 3,6' (Số CK × Dài × Rộng × Cao)."""
    text = (d.get("text") or "").strip()
    expr = (d.get("expr") or "").strip().replace(".", ",")
    dims = [_fmt_num(d.get(k)) for k in ("n", "l", "w", "h") if d.get(k) not in (None, "")]
    calc = ""
    if expr:
        calc = (f"{dims[0]} x " if d.get("n") not in (None, "") else "") + expr
    elif dims:
        calc = " x ".join(dims)
    if text and calc:
        return f"  - {text}: {calc}"
    return f"  - {text or calc}"


def _vnd(v: Decimal) -> str:
    return f"{int(v):,}".replace(",", ".") + " đồng"


def _equipment_after_tax(e) -> Decimal:
    from apps.projects.serializers import EquipmentCostSerializer

    a, v = EquipmentCostSerializer._amounts(e)
    return a + v


def _sheet_cover(wb: Workbook, run: CalculationRun, sample_note: str):
    rev = run.revision
    project = rev.project
    s = run.result["summary"]
    total = Decimal(s["values"]["TONG"])
    eq_total = sum((_equipment_after_tax(e) for e in rev.equipment.all()), Decimal(0))
    ws = wb.create_sheet("Bia", 0)
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 70
    ws.sheet_view.showGridLines = False
    big = Font(bold=True, size=20)
    r = 3
    if project.investor:
        ws.cell(row=r, column=2, value=safe(f"CHỦ ĐẦU TƯ: {project.investor.upper()}")).font = BOLD
        r += 1
    if project.consultant:
        ws.cell(row=r, column=2, value=safe(f"ĐƠN VỊ LẬP: {project.consultant.upper()}")).font = BOLD
    ws.cell(row=8, column=2, value="HỒ SƠ DỰ TOÁN XÂY DỰNG").font = big
    rows = [
        ("Công trình", project.name),
        ("Mã công trình", project.code),
        ("Địa điểm xây dựng", project.location),
        ("Chủ đầu tư", project.investor),
        ("Đơn vị lập dự toán", project.consultant),
        ("Bản dự toán", f"{rev.title or 'Dự toán lần ' + str(rev.number)} ({STATUS_VI.get(rev.status, rev.status)})"),
        ("Chi phí xây dựng (sau thuế, kể cả nhà tạm)", _vnd(total)),
        ("Chi phí thiết bị (sau thuế)", _vnd(eq_total)),
        ("Giá trị dự toán", _vnd(total + eq_total)),
        ("Bằng chữ", vnd_in_words(total + eq_total)),
    ]
    r = 11
    for k, v in rows:
        ws.cell(row=r, column=2, value=k).font = BOLD
        c = ws.cell(row=r, column=3, value=safe(v or ""))
        c.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    if sample_note:
        ws.cell(row=r + 1, column=2, value=sample_note).font = Font(bold=True, color="C00000")
    r += 4
    ws.cell(row=r, column=2, value="NGƯỜI LẬP").font = BOLD
    ws.cell(row=r, column=3, value="NGƯỜI KIỂM TRA / CHỦ TRÌ").font = BOLD
    ws.cell(row=r + 4, column=2, value=safe(project.preparer or ""))
    ws.cell(row=r + 4, column=3, value=safe(project.checker or ""))


def _sheet_items(wb: Workbook, run: CalculationRun, sample_note: str):
    """TH chi phí xây dựng theo hạng mục (giá trị engine) + tổng bằng chữ."""
    project = run.revision.project
    s = run.result["summary"]
    ws = wb.create_sheet("THChiPhiXD")
    _title(ws, "BẢNG TỔNG HỢP CHI PHÍ XÂY DỰNG THEO HẠNG MỤC", project.name, sample_note)
    _header(
        ws,
        5,
        [
            "STT",
            "Hạng mục",
            "Chi phí trực tiếp T",
            "Gián tiếp GT",
            "TN chịu thuế TL",
            "Trước thuế",
            "Thuế GTGT",
            "Sau thuế",
        ],
        [6, 46, 18, 16, 16, 18, 16, 18],
    )
    order = {str(i.id): (i.order, i.id) for i in run.revision.items.all()}
    items = sorted(s.get("items", []), key=lambda it: order.get(it["item_id"], (0, 0)))
    r = 6
    for i, it in enumerate(items, 1):
        v = it["values"]
        vals = [i, it["name"], num(v["T"]), num(v["GT"]), num(v["TL"]), num(v["GXDTT"]), num(v["GTGT"]), num(v["GXD"])]
        for c, val in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=safe(val))
            cell.border = BORDER
            if c >= 3:
                cell.number_format = VND
        r += 1
    ws.cell(row=r, column=2, value="TỔNG CỘNG CÁC HẠNG MỤC").font = BOLD
    for c in range(3, 9):
        col = get_column_letter(c)
        cell = ws.cell(row=r, column=c, value=f"=SUM({col}6:{col}{r - 1})" if r > 6 else 0)
        cell.font = BOLD
        cell.number_format = VND
        cell.border = BORDER
    r += 2
    ws.cell(row=r, column=2, value="Tổng chi phí XD sau thuế (toàn công trình, Bảng 3.8)").font = BOLD
    ws.cell(row=r, column=8, value=num(s["values"]["GXD"])).number_format = VND
    r += 1
    ws.cell(row=r, column=2, value="Bằng chữ:").font = BOLD
    ws.cell(row=r, column=3, value=vnd_in_words(s["values"]["GXD"]))
    r += 1
    ws.cell(
        row=r,
        column=2,
        value="Ghi chú: tỷ lệ chọn theo quy mô cả công trình rồi áp cho từng hạng mục; "
        "do làm tròn từng bước, tổng các hạng mục có thể lệch vài đồng so với dòng toàn công trình.",
    ).font = DETAIL_FONT


def _sheet_equipment(wb: Workbook, run: CalculationRun, sample_note: str):
    rev = run.revision
    equipment = list(rev.equipment.all())
    ws = wb.create_sheet("ChiPhiThietBi")
    _title(ws, "BẢNG TỔNG HỢP CHI PHÍ THIẾT BỊ", rev.project.name, sample_note)
    _header(
        ws,
        5,
        [
            "STT",
            "Tên thiết bị",
            "Đơn vị",
            "Số lượng",
            "Đơn giá trước thuế",
            "Thành tiền trước thuế",
            "Thuế suất",
            "Thuế GTGT",
            "Sau thuế",
            "Ghi chú",
        ],
        [6, 46, 8, 10, 18, 18, 10, 16, 18, 30],
    )
    r = 6
    for i, eq in enumerate(equipment, 1):
        vals = [i, eq.name, eq.unit, num(eq.quantity), num(eq.unit_price)]
        for c, v in enumerate(vals, 1):
            ws.cell(row=r, column=c, value=safe(v)).border = BORDER
        ws.cell(row=r, column=6, value=f"=ROUND(D{r}*E{r},0)")
        ws.cell(row=r, column=7, value=num(eq.vat_rate)).number_format = "0%"
        ws.cell(row=r, column=8, value=f"=ROUND(F{r}*G{r},0)")
        ws.cell(row=r, column=9, value=f"=F{r}+H{r}")
        ws.cell(row=r, column=10, value=safe(eq.note))
        for c in range(5, 11):
            ws.cell(row=r, column=c).border = BORDER
        for c in (5, 6, 8, 9):
            ws.cell(row=r, column=c).number_format = VND
        r += 1
    ws.cell(row=r, column=2, value="TỔNG CỘNG").font = BOLD
    for c in (6, 8, 9):
        col = get_column_letter(c)
        cell = ws.cell(row=r, column=c, value=f"=SUM({col}6:{col}{r - 1})" if r > 6 else 0)
        cell.font = BOLD
        cell.number_format = VND


def build_workbook(run: CalculationRun) -> Workbook:
    rev = run.revision
    project = rev.project
    summary = run.result["summary"]
    totals = run.result["resource_totals"]
    lines = list(
        run.lines.select_related("line__item", "line__work_item").order_by(
            "line__item__order", "line__order", "line_id"
        )
    )
    is_sample = project.norm_release.is_sample or project.price_release.is_sample
    sample_note = "DỮ LIỆU MẪU – KHÔNG DÙNG CHO HỒ SƠ THẬT" if is_sample else ""

    wb = Workbook()

    # ---------------- ThamSo
    ws = wb.active
    ws.title = "ThamSo"
    _title(ws, "THAM SỐ TÍNH TOÁN", project.name, sample_note)
    params = [
        ("Rule pack", f"{summary['rule_pack']['code']} v{summary['rule_pack']['version']}"),
        ("Căn cứ", summary["table"]),
        ("Loại công trình", project.get_construction_type_display()),
        ("Tỷ lệ chi phí chung (%)", num(summary["overhead"]["rate_pct"])),
        (
            "Cơ sở chi phí chung",
            "Nhân công (Bảng 3.4)" if summary["overhead"]["basis"] == "LABOR" else "Trực tiếp (Bảng 3.3)",
        ),
        ("Tỷ lệ CV không xác định được KL (%)", num(next(r["rate_pct"] for r in summary["rows"] if r["key"] == "TT"))),
        (
            "Tỷ lệ thu nhập chịu thuế tính trước (%)",
            num(next(r["rate_pct"] for r in summary["rows"] if r["key"] == "TL")),
        ),
        ("Thuế GTGT (%)", num(Decimal(summary["vat_rate"]) * 100)),
        ("Tỷ lệ nhà tạm (%)", num(summary["temp_housing"]["rate_pct"])),
        ("Engine version", run.engine_version),
        ("Input hash", run.input_hash),
        ("Output hash", run.output_hash),
        ("Bộ định mức", str(project.norm_release)),
        ("Bộ giá", f"{project.price_release} / {project.region} / {project.price_period}"),
    ]
    _header(ws, 5, ["Tham số", "Giá trị"], [45, 70])
    for i, (k, v) in enumerate(params, 6):
        ws.cell(row=i, column=1, value=k).border = BORDER
        ws.cell(row=i, column=2, value=safe(v)).border = BORDER
    P = {"C": "ThamSo!$B$9", "TT": "ThamSo!$B$11", "TL": "ThamSo!$B$12", "VAT": "ThamSo!$B$13", "LT": "ThamSo!$B$14"}
    amount_r = int(summary["rounding"]["amount"])

    # ---------------- TienLuong
    ws = wb.create_sheet("TienLuong")
    _title(ws, "BẢNG TIÊN LƯỢNG - DỰ TOÁN CHI PHÍ XÂY DỰNG", project.name, sample_note)
    _header(
        ws,
        5,
        [
            "STT",
            "Mã hiệu",
            "Tên công tác",
            "Đơn vị",
            "Khối lượng",
            "ĐG Vật liệu",
            "ĐG Nhân công",
            "ĐG Máy",
            "TT Vật liệu",
            "TT Nhân công",
            "TT Máy",
            "Thành tiền",
        ],
        [6, 12, 50, 8, 12, 14, 14, 14, 16, 16, 16, 18],
    )
    r = 6
    first_data_row = r
    current_item = None
    stt = 0
    for cl in lines:
        ln = cl.line
        if ln.item_id != current_item:
            current_item = ln.item_id
            ws.cell(row=r, column=3, value=safe(ln.item.name)).font = BOLD
            r += 1
        stt += 1
        vals = [stt, ln.code, ln.name, ln.unit, num(cl.quantity), num(cl.unit_vl), num(cl.unit_nc), num(cl.unit_m)]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=safe(v))
            cell.border = BORDER
        knc, km = Decimal(str(ln.k_nc)), Decimal(str(ln.k_m))
        ws.cell(row=r, column=9, value=f"=ROUND(E{r}*F{r},{amount_r})")
        ws.cell(row=r, column=10, value=f"=ROUND(E{r}*G{r}*{knc},{amount_r})")
        ws.cell(row=r, column=11, value=f"=ROUND(E{r}*H{r}*{km},{amount_r})")
        ws.cell(row=r, column=12, value=f"=I{r}+J{r}+K{r}")
        for c in range(9, 13):
            ws.cell(row=r, column=c).border = BORDER
        ws.cell(row=r, column=5).number_format = QTY
        for c in range(6, 13):
            ws.cell(row=r, column=c).number_format = VND
        line_row = r
        r += 1
        details = ln.details or []
        if details:
            first_detail = r
            for d in details:
                ws.cell(row=r, column=3, value=safe(_detail_text(d))).font = DETAIL_FONT
                if d.get("value") is not None:
                    cell = ws.cell(row=r, column=5, value=num(d["value"]))
                    cell.number_format = QTY
                    cell.font = DETAIL_FONT
                r += 1
            qty_r = int(summary["rounding"]["quantity"])
            ws.cell(row=line_row, column=5, value=f"=ROUND(SUM(E{first_detail}:E{r - 1}),{qty_r})")
    last_data_row = r - 1
    ws.cell(row=r, column=3, value="TỔNG CỘNG").font = BOLD
    for c, col in ((9, "I"), (10, "J"), (11, "K"), (12, "L")):
        cell = ws.cell(row=r, column=c, value=f"=SUM({col}{first_data_row}:{col}{last_data_row})")
        cell.font = BOLD
        cell.number_format = VND
        cell.border = BORDER
    tl_total_row = r
    ws.freeze_panes = "A6"

    # ---------------- PhanTichVatTu
    ws = wb.create_sheet("PhanTichVatTu")
    _title(ws, "BẢNG PHÂN TÍCH VẬT TƯ", project.name, sample_note)
    _header(
        ws,
        5,
        [
            "STT",
            "Mã hiệu",
            "Tên công tác / vật tư",
            "Đơn vị",
            "Định mức",
            "Khối lượng",
            "Hao phí",
            "Đơn giá",
            "Thành tiền",
        ],
        [6, 14, 50, 8, 12, 12, 14, 14, 16],
    )
    r = 6
    stt = 0
    cons_r = int(summary["rounding"]["norm_consumption"])
    for cl in lines:
        ln = cl.line
        stt += 1
        for c, v in enumerate([stt, ln.code, ln.name, ln.unit, None, num(cl.quantity)], 1):
            cell = ws.cell(row=r, column=c, value=safe(v))
            cell.font = BOLD
            cell.border = BORDER
        qty_row = r
        r += 1
        for comp in cl.breakdown["components"]:
            if "other_pct" in comp:
                ws.cell(
                    row=r, column=3, value=f"{'Vật liệu' if comp['kind'] == 'MATERIAL' else 'Máy'} khác"
                ).border = BORDER
                ws.cell(row=r, column=4, value="%").border = BORDER
                ws.cell(row=r, column=5, value=num(comp["other_pct"])).border = BORDER
                r += 1
                continue
            vals = [
                None,
                comp["resource_code"],
                comp["name"] or comp["resource_code"],
                comp["unit"],
                num(comp["norm_qty"]),
            ]
            for c, v in enumerate(vals, 1):
                ws.cell(row=r, column=c, value=safe(v)).border = BORDER
            ws.cell(row=r, column=7, value=f"=ROUND(E{r}*$F${qty_row},{cons_r})").border = BORDER
            ws.cell(row=r, column=8, value=num(comp["price"])).border = BORDER
            ws.cell(row=r, column=9, value=f"=ROUND(G{r}*H{r},{amount_r})").border = BORDER
            ws.cell(row=r, column=7).number_format = CONS
            ws.cell(row=r, column=8).number_format = VND
            ws.cell(row=r, column=9).number_format = VND
            r += 1
    ws.freeze_panes = "A6"

    # ---------------- TongHopVatTu
    ws = wb.create_sheet("TongHopVatTu")
    _title(ws, "BẢNG TỔNG HỢP VẬT TƯ", project.name, sample_note)
    _header(
        ws,
        5,
        ["STT", "Mã", "Tên vật tư / nhân công / máy", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền", "Nguồn giá"],
        [6, 14, 50, 8, 14, 14, 18, 40],
    )
    r = 6
    kind_label = {"MATERIAL": "I. VẬT LIỆU", "LABOR": "II. NHÂN CÔNG", "MACHINE": "III. MÁY THI CÔNG"}
    first = r
    for kind in ("MATERIAL", "LABOR", "MACHINE"):
        ws.cell(row=r, column=3, value=kind_label[kind]).font = BOLD
        r += 1
        stt = 0
        for t in (t for t in totals if t["kind"] == kind):
            stt += 1
            for c, v in enumerate(
                [stt, t["resource_code"], t["name"], t["unit"], num(t["quantity"]), num(t["price"])], 1
            ):
                ws.cell(row=r, column=c, value=safe(v)).border = BORDER
            ws.cell(row=r, column=7, value=f"=ROUND(E{r}*F{r},{amount_r})").border = BORDER
            ws.cell(row=r, column=8, value=safe(t["price_source"])).border = BORDER
            ws.cell(row=r, column=5).number_format = CONS
            ws.cell(row=r, column=6).number_format = VND
            ws.cell(row=r, column=7).number_format = VND
            r += 1
    ws.cell(row=r, column=3, value="TỔNG CỘNG").font = BOLD
    ws.cell(row=r, column=7, value=f"=SUM(G{first}:G{r - 1})").font = BOLD
    ws.cell(row=r, column=7).number_format = VND
    ws.freeze_panes = "A6"

    # ---------------- TongHopKinhPhi (Bảng 3.8)
    ws = wb.create_sheet("TongHopKinhPhi")
    _title(
        ws, "BẢNG TỔNG HỢP DỰ TOÁN CHI PHÍ XÂY DỰNG (Bảng 3.8 Phụ lục III TT 36/2026/TT-BXD)", project.name, sample_note
    )
    _header(
        ws,
        5,
        ["STT", "NỘI DUNG CHI PHÍ", "CÁCH TÍNH", "GIÁ TRỊ (Excel)", "GIÁ TRỊ (Engine)", "KÝ HIỆU"],
        [6, 60, 34, 20, 20, 10],
    )
    TL = "TienLuong"
    rows_xl = {
        "VL": f"={TL}!I{tl_total_row}",
        "NC": f"={TL}!J{tl_total_row}",
        "M": f"={TL}!K{tl_total_row}",
    }
    row_of: dict[str, int] = {}
    r = 6
    for item in summary["rows"]:
        key = item["key"]
        row_of[key] = r
        ws.cell(row=r, column=1, value=item["stt"]).border = BORDER
        ws.cell(row=r, column=2, value=safe(item["label"])).border = BORDER
        ws.cell(row=r, column=3, value=safe(item["formula"])).border = BORDER
        ws.cell(row=r, column=5, value=num(item["value"])).border = BORDER
        ws.cell(row=r, column=6, value=key).border = BORDER
        ws.cell(row=r, column=4).border = BORDER
        ws.cell(row=r, column=4).number_format = VND
        ws.cell(row=r, column=5).number_format = VND
        if key in ("T", "GT", "GXDTT", "GXD", "TONG"):
            for c in range(1, 7):
                ws.cell(row=r, column=c).font = BOLD
        r += 1
    R = lambda k: f"D{row_of[k]}"  # noqa: E731
    overhead_base = R("NC") if summary["overhead"]["basis"] == "LABOR" else R("T")
    formulas = {
        "VL": rows_xl["VL"],
        "NC": rows_xl["NC"],
        "M": rows_xl["M"],
        "T": f"={R('VL')}+{R('NC')}+{R('M')}",
        "C": f"=ROUND({overhead_base}*{P['C']}/100,{amount_r})",
        "TT": f"=ROUND({R('T')}*{P['TT']}/100,{amount_r})",
        "GT": f"={R('C')}+{R('TT')}",
        "TL": f"=ROUND(({R('T')}+{R('GT')})*{P['TL']}/100,{amount_r})",
        "GXDTT": f"={R('T')}+{R('GT')}+{R('TL')}",
        "GTGT": f"=ROUND({R('GXDTT')}*{P['VAT']}/100,{amount_r})",
        "GXD": f"={R('GXDTT')}+{R('GTGT')}",
        "LT": f"=ROUND({R('GXDTT')}*{P['LT']}/100,{amount_r})",
        "LT_GTGT": f"=ROUND({R('LT')}*{P['VAT']}/100,{amount_r})",
        "LT_SAU_THUE": f"={R('LT')}+{R('LT_GTGT')}",
        "TONG": f"={R('GXD')}+{R('LT_SAU_THUE')}",
    }
    for key, f in formulas.items():
        ws.cell(row=row_of[key], column=4, value=f)
    ws.cell(row=r, column=2, value="Bằng chữ (tổng sau thuế kể cả nhà tạm):").font = BOLD
    ws.cell(row=r, column=3, value=vnd_in_words(summary["values"]["TONG"]))
    r += 2
    ws.cell(row=r, column=2, value="NGƯỜI LẬP").font = BOLD
    ws.cell(row=r, column=5, value="NGƯỜI CHỦ TRÌ").font = BOLD
    ws.cell(row=r + 4, column=2, value=safe(project.preparer or ""))
    ws.cell(row=r + 4, column=5, value=safe(project.checker or ""))
    r += 4
    if run.warnings:
        r += 3
        ws.cell(row=r, column=2, value="CẢNH BÁO TỪ HỆ THỐNG").font = BOLD
        for w in run.warnings:
            r += 1
            ws.cell(row=r, column=2, value=safe(f"[{w.get('code')}] {w.get('message')}"))

    _sheet_items(wb, run, sample_note)
    _sheet_equipment(wb, run, sample_note)
    _sheet_cover(wb, run, sample_note)
    return wb


def workbook_bytes(run: CalculationRun) -> bytes:
    buf = BytesIO()
    build_workbook(run).save(buf)
    return buf.getvalue()
