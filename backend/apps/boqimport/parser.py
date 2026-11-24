"""Đọc một file Excel BoQ bất kỳ (bóc từ bản vẽ) thành danh sách hạng mục + dòng công tác.

Không đòi file theo mẫu: tự dò dòng tiêu đề và các cột (STT, mã hiệu, tên công tác, đơn vị, khối lượng)
theo từ khóa; người dùng có thể chỉ định lại sheet / dòng tiêu đề / cột khi hệ thống đoán sai.

Quy tắc phân loại dòng dưới tiêu đề:
- có tên + đơn vị (+ khối lượng)      → dòng công tác;
- có tên, không đơn vị, không KL      → tiêu đề hạng mục (trừ dòng "-"/"+" ngay sau một công tác: ghi chú);
- có tên + KL, không đơn vị, không STT → dòng diễn giải khối lượng của công tác ngay trên;
- dòng "Tổng / Cộng"                  → bỏ qua.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from apps.calculation.engine.quantity import QuantityError, evaluate

from .units import strip_accents

MAX_ROWS = 5000
FIELDS = ("stt", "code", "name", "unit", "qty", "item")

# Từ khóa tiêu đề (đã bỏ dấu, viết thường). Thứ tự = ưu tiên.
_HEADER_KEYS: dict[str, list[str]] = {
    "stt": ["stt", "so tt", "tt"],
    "code": ["ma hieu dinh muc", "ma dinh muc", "ma hieu", "ma dm", "ma cong tac", "ma hieu dg", "ma so", "ma"],
    "name": [
        "ten cong tac",
        "noi dung cong viec",
        "noi dung",
        "ten cong viec",
        "danh muc cong viec",
        "hang muc cong viec",
        "mo ta",
        "dien giai",
        "cong tac",
        "ten",
    ],
    "unit": ["don vi tinh", "don vi", "dvt", "dv"],
    # Cột hạng mục riêng (mỗi dòng ghi tên hạng mục) — thay cho dòng tiêu đề hạng mục
    "item": ["hang muc cong trinh", "hang muc"],
    "qty": ["khoi luong toan bo", "tong khoi luong", "khoi luong", "kl", "so luong", "tong"],
}
_TOTAL_ROW = re.compile(r"^\s*(tong cong|tong so|cong|tong)\b")
_ROMAN = re.compile(r"^(?=[ivxlc]+\.?$)[ivxlc]+\.?$", re.I)


class BoqParseError(ValueError):
    pass


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _key(v) -> str:
    return strip_accents(_text(v)).lower()


def parse_number(v) -> Decimal | None:
    """12,5 / 1.234,5 / 1,234.5 / 12.5 / 7 → Decimal; chuỗi rỗng hoặc chữ → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float | Decimal):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if not s or not re.fullmatch(r"-?[\d.,]+", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        # 1,234 (nghìn) hay 12,5 (thập phân)? Kiểu Việt Nam: dấu phẩy là thập phân trừ khi đúng nhóm 3 chữ số
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) and s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


@dataclass
class ParsedLine:
    row: int
    stt: str
    code: str
    name: str
    unit: str
    quantity: Decimal | None
    details: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedItem:
    row: int | None
    name: str
    lines: list[ParsedLine] = field(default_factory=list)


@dataclass
class ParsedBoq:
    sheets: list[str]
    sheet: str
    header_row: int
    columns: dict[str, int | None]  # field → chỉ số cột 1-based
    headers: list[dict]
    items: list[ParsedItem]
    skipped: list[dict]
    warnings: list[str]


def _score_header(cells: list[str]) -> tuple[int, dict[str, int]]:
    found: dict[str, int] = {}
    score = 0
    for f in FIELDS:
        best: tuple[int, int] | None = None  # (độ ưu tiên, cột)
        for col, text in enumerate(cells, 1):
            if not text or len(text) > 60:
                continue
            for prio, kw in enumerate(_HEADER_KEYS[f]):
                if text == kw or text.startswith(kw + " ") or (len(kw) > 3 and kw in text):
                    if col in found.values():
                        continue
                    cand = (prio, col)
                    if best is None or cand < best:
                        best = cand
                    break
        if best is not None:
            found[f] = best[1]
            score += 3 if f in ("name", "unit", "qty") else 1
    return score, found


def _detect(ws, header_row: int | None) -> tuple[int, dict[str, int], int]:
    """→ (dòng tiêu đề, {trường: cột}, dòng dữ liệu đầu tiên)."""
    rows = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 40), values_only=True))
    best: tuple[int, int, dict[str, int], int] = (0, 0, {}, 0)
    for r, values in enumerate(rows, 1):
        if header_row and r != header_row:
            continue
        cells = [_key(v) for v in values]
        own_score, own = _score_header(cells)
        if own_score == 0:
            continue
        score, found, start = own_score, own, r + 1
        # Tiêu đề hai tầng: "Khối lượng" gộp ngang nhiều ô, tầng dưới "Một cấu kiện | Toàn bộ".
        # Nhận ra khi dòng dưới có chữ nằm dưới phần kéo dài của một ô gộp (ô trên trống, bên trái có chữ).
        if r < len(rows):
            below = [_key(v) for v in rows[r]]
            top, carry, spans = [], "", False
            for i, a in enumerate(cells):
                b = below[i] if i < len(below) else ""
                if a:
                    carry = a
                elif b and carry and not _looks_numeric(b):
                    spans = True
                top.append(a or (carry if b else ""))
            # Dòng dữ liệu (có số) không bao giờ là tầng tiêu đề dưới
            if spans and not any(_looks_numeric(x) for x in below if x):
                merged = [
                    f"{a} {b}".strip() if b and not _looks_numeric(b) else a for a, b in zip(top, below, strict=False)
                ]
                m_score, m_found = _score_header(merged)
                if m_score >= own_score:
                    score, found, start = m_score, m_found, r + 2
        if score > best[0]:
            best = (score, r, found, start)
    score, r, found, start = best
    if header_row and not r:
        return header_row, {}, header_row + 1
    if score < 7 or "name" not in found:
        raise BoqParseError(
            "Không tìm thấy dòng tiêu đề có cột Tên công tác, Đơn vị và Khối lượng. "
            "Hãy chọn sheet / dòng tiêu đề / cột bằng tay."
        )
    return r, found, start


_NUMBERING = re.compile(r"^\s*(?:[IVXLC]+|[A-Z]|\d+(?:\.\d+)*)\s*[.)\-:]\s+(?=\S)")


def _strip_numbering(s: str) -> str:
    """ "I. HỆ THỐNG CAMERA" / "A - PHẦN MÓNG" → tên hạng mục không kèm số thứ tự."""
    return _NUMBERING.sub("", s, count=1).strip()


def _looks_numeric(s: str) -> bool:
    return bool(re.fullmatch(r"[\d.,\s()]+", s or ""))


def parse_workbook(
    data: bytes,
    sheet: str | None = None,
    header_row: int | None = None,
    columns: dict[str, int | None] | None = None,
) -> ParsedBoq:
    try:
        wb_val = load_workbook(BytesIO(data), data_only=True, read_only=False)
        wb_formula = load_workbook(BytesIO(data), data_only=False, read_only=False)
    except Exception as e:  # noqa: BLE001 — mọi lỗi đọc file đều trả cùng một thông báo dễ hiểu
        raise BoqParseError(
            "Không đọc được file. Chỉ hỗ trợ Excel .xlsx/.xlsm; file .xls cũ hãy mở bằng Excel và Lưu thành .xlsx."
        ) from e
    sheets = wb_val.sheetnames
    warnings: list[str] = []

    if sheet and sheet not in sheets:
        raise BoqParseError(f"Không có sheet “{sheet}”")
    candidates = [sheet] if sheet else sheets
    detected = None
    errors = []
    for name in candidates:
        try:
            hr, found, start = _detect(wb_val[name], header_row)
            detected = (name, hr, found, start)
            break
        except BoqParseError as e:
            errors.append(str(e))
    if detected is None:
        if columns and header_row:
            detected = (candidates[0], header_row, {}, header_row + 1)
        else:
            raise BoqParseError(errors[0] if errors else "File rỗng")
    sheet_name, hr, found, start = detected
    cols: dict[str, int | None] = {f: found.get(f) for f in FIELDS}
    if columns:
        for f in FIELDS:
            if f in columns:
                cols[f] = columns[f] or None
    if not cols.get("name"):
        raise BoqParseError("Cần chọn cột Tên công tác")
    if not cols.get("qty"):
        warnings.append("Không thấy cột Khối lượng — các dòng sẽ có khối lượng 0.")

    ws = wb_val[sheet_name]
    wsf = wb_formula[sheet_name]
    header_vals = next(ws.iter_rows(min_row=hr, max_row=hr, values_only=True), ())
    headers = [{"col": i, "letter": get_column_letter(i), "text": _text(v)} for i, v in enumerate(header_vals, 1)]

    def cell(values, f):
        c = cols.get(f)
        return values[c - 1] if c and c - 1 < len(values) else None

    items: list[ParsedItem] = []
    skipped: list[dict] = []
    current: ParsedItem | None = None
    last: ParsedLine | None = None
    max_row = min(ws.max_row or hr, start + MAX_ROWS)
    if (ws.max_row or 0) > start + MAX_ROWS:
        warnings.append(f"File có hơn {MAX_ROWS} dòng; chỉ đọc {MAX_ROWS} dòng đầu.")

    for r, values in enumerate(ws.iter_rows(min_row=start, max_row=max_row, values_only=True), start):
        name = _text(cell(values, "name"))
        stt = _text(cell(values, "stt"))
        code = _text(cell(values, "code"))
        unit = _text(cell(values, "unit"))
        item_name = _text(cell(values, "item"))[:300]
        raw_qty = cell(values, "qty")
        qty = parse_number(raw_qty)
        qty_warning = None
        if qty is None and raw_qty is None and cols.get("qty"):
            f = wsf.cell(row=r, column=cols["qty"]).value
            if isinstance(f, str) and f.startswith("="):
                try:
                    qty = evaluate(f[1:])
                except QuantityError:
                    qty_warning = (
                        f"Ô khối lượng là công thức {f[:40]} chưa có giá trị (mở file bằng Excel, lưu lại rồi tải lên)"
                    )
        # Dòng tiêu đề lặp lại giữa file (thường ở đầu mỗi phần / mỗi trang in)
        if name and _score_header([_key(v) for v in values])[0] >= 7:
            skipped.append({"row": r, "reason": "Dòng tiêu đề lặp lại"})
            last = None
            continue
        if not name:
            if any(v not in (None, "") for v in values) and (unit or qty is not None):
                skipped.append({"row": r, "reason": "Thiếu tên công tác"})
                continue
            # Tiêu đề hạng mục ghi ở cột khác (vd ô gộp bắt đầu từ cột STT): "I. HỆ THỐNG CAMERA"
            texts = [
                _text(v) for v in values if isinstance(v, str) and len(_text(v)) >= 3 and not _looks_numeric(_text(v))
            ]
            if texts and qty is None and not unit and not _TOTAL_ROW.match(_key(texts[0])):
                current = ParsedItem(r, _strip_numbering(texts[0])[:300])
                items.append(current)
                last = None
            continue
        if _TOTAL_ROW.match(_key(name)) and not unit:
            skipped.append({"row": r, "reason": "Dòng tổng cộng"})
            continue
        if _looks_numeric(name) and (not unit or _looks_numeric(unit)):
            continue  # dòng đánh số cột (1) (2) (3)…

        if unit:
            ln = ParsedLine(r, stt, code, name, unit, qty)
            if qty is None:
                ln.warnings.append(qty_warning or "Thiếu khối lượng")
            if item_name and (current is None or current.name != item_name):
                current = next((it for it in items if it.name == item_name), None)
                if current is None:
                    current = ParsedItem(r, item_name)
                    items.append(current)
            if current is None:
                current = ParsedItem(None, "Hạng mục chung")
                items.append(current)
            current.lines.append(ln)
            last = ln
        elif qty is not None and not stt and last is not None:
            last.details.append({"text": name, "expr": format(qty, "f")})
        elif last is not None and not stt and name[:1] in "-+*•":
            skipped.append({"row": r, "reason": "Ghi chú dưới công tác"})
        else:
            current = ParsedItem(r, (_strip_numbering(name) or name)[:300])
            items.append(current)
            last = None

    # Diễn giải chỉ dùng khi khớp với khối lượng dòng chính (hoặc dòng chính để trống)
    for it in items:
        for ln in it.lines:
            if not ln.details:
                continue
            total = sum((Decimal(d["expr"]) for d in ln.details), Decimal(0))
            if ln.quantity is None:
                ln.quantity = total
                ln.warnings = [w for w in ln.warnings if w != "Thiếu khối lượng"]
            elif abs(total - ln.quantity) > max(abs(ln.quantity) * Decimal("0.005"), Decimal("0.001")):
                ln.warnings.append(
                    f"Tổng diễn giải ({total.normalize():f}) khác khối lượng dòng ({ln.quantity.normalize():f}); "
                    "dùng khối lượng dòng, bỏ diễn giải"
                )
                ln.details = []

    items = [it for it in items if it.lines]
    if not items:
        raise BoqParseError("Không tìm thấy dòng công tác nào (dòng có tên và đơn vị) dưới dòng tiêu đề.")
    return ParsedBoq(sheets, sheet_name, hr, cols, headers, items, skipped, warnings)
