"""Bóc tách định mức dự toán từ PDF Thông tư 38/2026/TT-BXD (8 phụ lục) theo tọa độ chữ.

Đầu vào: kết quả ``pdftotext -bbox`` (XHTML có tọa độ từng từ). Thuần Python, không dùng Django,
để kiểm thử độc lập. Mỗi bảng định mức có dạng:

    Mã hiệu | Công tác | Thành phần hao phí | Đơn vị | <cột 1> <cột 2> ...
    AF.111  | Bê tông  | Vật liệu            |        |
            |          | Vữa bê tông         | m3     | 1,025   1,025
            |          | Nhân công nhóm 2    | công   | 1,07    0,89
            |          | Máy thi công        |        |
            |          | Máy trộn 250l       | ca     | 0,095   0,095
                                                       10      20      ← số hiệu cột

→ AF.11110, AF.11120 (mã gốc + số hiệu cột). Ô "-" = không có hao phí ở cột đó.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

APPENDICES = {
    "I": "Định mức dự toán khảo sát xây dựng công trình",
    "II": "Định mức dự toán xây dựng công trình",
    "III": "Định mức dự toán lắp đặt hệ thống kỹ thuật của công trình",
    "IV": "Định mức dự toán lắp đặt máy và thiết bị công nghệ",
    "V": "Định mức dự toán thí nghiệm chuyên ngành xây dựng",
    "VI": "Định mức dự toán sửa chữa và bảo dưỡng công trình xây dựng",
    "VII": "Định mức sử dụng vật liệu xây dựng",
    "VIII": "Định mức chi phí quản lý dự án và tư vấn xây dựng",
}

# Ký tự font Symbol (vùng PUA U+F0xx) → Unicode
_SYMBOL = {0xA3: "≤", 0xB3: "≥", 0xB4: "×", 0xB1: "±", 0xB0: "°", 0xC6: "Ø", 0xE6: "", 0xF0: "", 0xB8: "÷", 0xD7: "×"}

WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
BASE_CODE_RE = re.compile(r"^(?:[A-Z]{2}\.\d{2,4}|\d{2}\.\d{3})$")
GROUP_CODE_RE = re.compile(r"^(?:[A-Z]{2}\.\d{5}|\d{2}\.\d{5})$")
SUFFIX_RE = re.compile(r"^\d{1,3}$")
NUM_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:,\d+)?$")
DASH = {"-", "–", "—"}
_HEADER_WORDS = {"việc", "tác", "dựng", "đặt", "lắp", "xây", "Tên", "Công", "công", "hiệu", "Mã", "trình", "Loại"}


def fix_text(s: str) -> str:
    s = html.unescape(s)
    out = []
    for ch in s:
        o = ord(ch)
        if 0xF000 <= o <= 0xF0FF:
            low = o - 0xF000
            out.append(_SYMBOL.get(low, chr(low) if 0x20 <= low < 0x7F else ""))
        else:
            out.append(ch)
    return "".join(out)


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    page: int

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Line:
    page: int
    y: float  # baseline-ish (y1 của từ cao nhất)
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Component:
    kind: str  # MATERIAL | LABOR | MACHINE
    name: str
    unit: str
    quantity: str  # chuỗi số dạng Decimal (dấu chấm)
    is_other_pct: bool = False


@dataclass
class NormRecord:
    code: str
    name: str
    unit: str
    appendix: str
    group_code: str
    group_name: str
    page: int
    components: list[Component] = field(default_factory=list)


@dataclass
class ParseReport:
    pages: int = 0
    tables: int = 0
    records: int = 0
    skipped_tables: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- words → lines


def read_pages(bbox_html: str) -> list[list[Word]]:
    pages = []
    for pno, chunk in enumerate(bbox_html.split("<page ")[1:], 1):
        words = []
        for x0, y0, x1, y1, t in WORD_RE.findall(chunk):
            t = fix_text(t).strip()
            if t:
                words.append(Word(float(x0), float(y0), float(x1), float(y1), t, pno))
        pages.append(words)
    return pages


def _merge_superscripts(words: list[Word]) -> list[Word]:
    """Chữ số nhỏ nâng cao ngay sau một từ (m³, m³/ph) → ghép vào từ đó."""
    normal = [w for w in words if not (w.h < 8.5 and w.text.isdigit() and len(w.text) <= 2)]
    for w in words:
        if w in normal:
            continue
        host = min(
            (n for n in normal if -0.5 <= w.x0 - n.x1 <= 2.0 and n.y0 - 2 <= w.y1 <= n.y1 + 1),
            key=lambda n: abs(w.x0 - n.x1),
            default=None,
        )
        if host is not None:
            host.text += w.text
            host.x1 = max(host.x1, w.x1)
        else:
            normal.append(w)
    return normal


def to_lines(words: list[Word]) -> list[Line]:
    """Gom từ thành dòng theo tọa độ y; ghép chỉ số trên (m + 3 → m3)."""
    words = _merge_superscripts(sorted(words, key=lambda w: (w.y0, w.x0)))
    lines: list[Line] = []
    for w in sorted(words, key=lambda w: w.y1):
        small = w.h < 8.5 and len(w.text) <= 2
        target = None
        for ln in reversed(lines[-4:]):
            tol = 7.5 if small else 3.2
            if abs(ln.y - w.y1) <= tol or (small and ln.y - 9 <= w.y1 <= ln.y + 1):
                target = ln
                break
        if target is None:
            lines.append(Line(w.page, w.y1, [w]))
        else:
            target.words.append(w)
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
        merged: list[Word] = []
        for w in ln.words:
            prev = merged[-1] if merged else None
            if prev and w.h < 8.5 and len(w.text) <= 2 and 0 <= w.x0 - prev.x1 <= 1.5 and w.text.isdigit():
                prev.text += w.text  # m + 3 → m3
                prev.x1 = w.x1
            else:
                merged.append(Word(w.x0, w.y0, w.x1, w.y1, w.text, w.page))
        ln.words = merged
    lines.sort(key=lambda ln: ln.y)
    return lines


def _num(s: str) -> str | None:
    s = s.strip()
    if not NUM_RE.match(s):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    return s


# --------------------------------------------------------------------------- table parsing


@dataclass
class _Geom:
    unit_x0: float
    unit_x1: float
    name_x0: float  # bắt đầu cột "Thành phần hao phí"
    work_x0: float  # bắt đầu cột công tác (sau mã hiệu)
    header_y: float


def _header_geom(line: Line, nearby: list[Line]) -> _Geom | None:
    """Dòng tiêu đề có 'Mã' + 'hiệu' / 'Đơn' + 'vị' + 'Thành phần'. Bỏ qua dòng "Đơn vị tính: ..."."""
    toks = [ln for ln in nearby if "tính" not in ln.text]
    unit = [w for ln in toks for w in ln.words if w.text in ("Đơn", "vị", "Đơn vị", "ĐV", "vị tính")]
    comp = [w for ln in toks for w in ln.words if w.text in ("Thành", "Loại", "Thành phần")]
    ma = [w for ln in toks for w in ln.words if w.text in ("Mã", "Mã hiệu")]
    if not unit or not ma:
        return None
    ux0 = min(w.x0 for w in unit) - 6
    ux1 = max(w.x1 for w in unit) + 6
    name_x0 = min(w.x0 for w in comp) - 4 if comp else ma[0].x1 + 20
    work_words = [w for ln in toks for w in ln.words if ma[0].x1 < w.x0 < name_x0 - 2]
    work_x0 = min((w.x0 for w in work_words), default=ma[0].x1 + 4) - 4
    if name_x0 >= ux0:
        name_x0 = work_x0
    return _Geom(ux0, ux1, name_x0, work_x0, line.y)


def _refine_geom(geom: _Geom, band: list[Line]) -> _Geom:
    """Mép trái cột tên hao phí = vị trí chữ "Vật liệu" / "Máy thi công" / "Nhân công" trong bảng."""
    xs = []
    for ln in band:
        for a, b in zip(ln.words, ln.words[1:], strict=False):
            if (a.text, b.text) in (("Vật", "liệu"), ("Máy", "thi"), ("Nhân", "công")) and a.x0 < geom.unit_x0:
                xs.append(a.x0)
    if xs:
        x = min(xs)
        if x > geom.work_x0 + 10 or geom.name_x0 > x:
            return _Geom(geom.unit_x0, geom.unit_x1, x - 2, min(geom.work_x0, x - 2), geom.header_y)
    return geom


def _is_category(text: str) -> str | None:
    t = text.strip().rstrip(":").lower()
    if t in ("vật liệu", "vật tư"):
        return "MATERIAL"
    if t in ("nhân công",):
        return "LABOR"
    if t in ("máy thi công", "máy và thiết bị thi công", "máy, thiết bị thi công", "thiết bị thi công"):
        return "MACHINE"
    return None


def _kind_for(name: str, current: str) -> str:
    n = name.lower()
    if n.startswith("nhân công") or n.startswith("kỹ sư") or n.startswith("công nhân"):
        return "LABOR"
    if n.startswith("máy khác") or n.startswith("máy thi công khác"):
        return "MACHINE"
    if n.startswith("vật liệu khác"):
        return "MATERIAL"
    return current


def parse_tables(lines: list[Line], appendix_of_page, report: ParseReport) -> list[NormRecord]:
    records: list[NormRecord] = []
    geom: _Geom | None = None
    heading_code, heading_name = "", ""
    unit_of_work = ""
    band: list[Line] = []
    in_table = False

    def flush(suffix_line: Line):
        nonlocal band
        if geom is None:
            band = []
            return
        recs = _parse_band(band, suffix_line, geom, heading_code, heading_name, unit_of_work, appendix_of_page, report)
        records.extend(recs)
        band = []

    for i, ln in enumerate(lines):
        txt = ln.text
        first = ln.words[0]
        # tiêu đề nhóm: "AF.11100 BÊ TÔNG LÓT MÓNG" (ở lề trái, ngoài bảng)
        if GROUP_CODE_RE.match(first.text) and len(ln.words) > 1 and not in_table:
            heading_code = first.text
            heading_name = " ".join(w.text for w in ln.words[1:])
            # tiêu đề xuống dòng
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if (
                nxt
                and nxt.page == ln.page
                and 0 < nxt.y - ln.y < 16
                and nxt.text.isupper()
                and "Đơn vị" not in nxt.text
            ):
                heading_name += " " + nxt.text
            continue
        m = re.search(r"Đơn vị tính\s*:?\s*(.+)$", txt)
        if m and not in_table:
            unit_of_work = m.group(1).strip()
            continue
        if any(w.text in ("Mã", "Mã hiệu") for w in ln.words) and not in_table:
            nearby = [x for x in lines[max(0, i - 3) : i + 4] if x.page == ln.page and abs(x.y - ln.y) < 30]
            g = _header_geom(ln, nearby)
            if g:
                geom = g
                in_table = True
                band = [
                    x
                    for x in lines[max(0, i - 3) : i + 1]
                    if x.page == ln.page and abs(x.y - ln.y) < 30 and "tính" not in x.text
                ]
                continue
        if in_table or geom is not None:
            # hàng số hiệu cột: toàn số 1-3 chữ số, nằm bên phải cột đơn vị
            if geom and all(SUFFIX_RE.match(w.text) for w in ln.words) and min(w.x0 for w in ln.words) > geom.unit_x0:
                if band and _has_data(band, geom):
                    flush(ln)
                    in_table = False
                    continue
            if in_table:
                band.append(ln)
                if len(band) > 400:
                    report.skipped_tables.append(f"p{ln.page}: bảng quá dài, bỏ qua")
                    band, in_table = [], False
    return records


def _has_data(band: list[Line], geom: _Geom) -> bool:
    """Đã có ít nhất một dòng hao phí (đơn vị + số) — tránh nhầm tiêu đề cột "1 2 3 4" là hàng số hiệu."""
    for ln in band:
        if any(geom.unit_x0 <= w.xc <= geom.unit_x1 for w in ln.words) and any(
            _num(w.text) is not None for w in ln.words if w.x0 > geom.unit_x1
        ):
            return True
    return False


def _parse_band(band, suffix_line, geom: _Geom, heading_code, heading_name, unit_of_work, appendix_of_page, report):
    report.tables += 1
    geom = _refine_geom(geom, band)
    cols = [(w.xc, w.text) for w in suffix_line.words]
    spacing = min((b[0] - a[0] for a, b in zip(cols, cols[1:], strict=False)), default=80)
    tol = max(spacing / 2, 18)

    def col_of(x: float) -> int | None:
        best = min(range(len(cols)), key=lambda k: abs(cols[k][0] - x))
        return best if abs(cols[best][0] - x) <= tol else None

    # ---- tách phần tiêu đề cột (trước dòng dữ liệu đầu tiên)
    data_start = None
    for idx, ln in enumerate(band):
        names = " ".join(x.text for x in ln.words if x.x0 >= geom.name_x0 - 2 and x.xc < geom.unit_x0)
        unit_txt = " ".join(w.text for w in ln.words if geom.unit_x0 <= w.xc <= geom.unit_x1)
        if names.strip().lower() in ("hao phí", "phần hao phí", "thành phần hao phí") or unit_txt in (
            "vị",
            "Đơn",
            "tính",
        ):
            continue  # vẫn là dòng tiêu đề (có nhãn cột dạng số)
        has_unit = any(geom.unit_x0 <= w.xc <= geom.unit_x1 for w in ln.words)
        has_val = any(_num(w.text) is not None or w.text in DASH for w in ln.words if w.x0 > geom.unit_x1)
        if (has_unit and has_val) or _is_category(names):
            data_start = idx
            break
    if data_start is None:
        report.skipped_tables.append(f"p{suffix_line.page}: không thấy dòng số liệu ({heading_code})")
        return []
    header_lines = band[:data_start]
    col_labels = [[] for _ in cols]
    span_label: list[str] = []
    for ln in header_lines:
        right = [w for w in ln.words if w.x0 > geom.unit_x1 - 2]
        # gom từ liền nhau thành cụm
        clusters: list[list[Word]] = []
        for w in right:
            if clusters and w.x0 - clusters[-1][-1].x1 < 6:
                clusters[-1].append(w)
            else:
                clusters.append([w])
        for c in clusters:
            text = " ".join(w.text for w in c)
            x0, x1 = c[0].x0, c[-1].x1
            covered = [k for k, (cx, _) in enumerate(cols) if x0 - 4 <= cx <= x1 + 4]
            if len(covered) >= 2 or (len(cols) > 1 and not covered and (x1 - x0) > spacing):
                span_label.append(text)
            else:
                k = col_of((x0 + x1) / 2)
                if k is not None:
                    col_labels[k].append(text)

    # ---- dòng dữ liệu
    rows = band[data_start:]
    codes: list[tuple[float, str, int]] = []  # (y, base code, page)
    work_text: list[tuple[float, str]] = []
    items: list[dict] = []  # {y, kind?, name, unit, vals}
    kind = "MATERIAL"
    for ln in rows:
        code_w = [w for w in ln.words if w.xc < geom.name_x0 and BASE_CODE_RE.match(w.text)]
        for w in code_w:
            codes.append((ln.y + ln.page * 10000, w.text, ln.page))
        work = [
            w
            for w in ln.words
            if w.x0 < geom.name_x0 - 2 and w not in code_w and not (len(work_text) < 2 and w.text in _HEADER_WORDS)
        ]
        if work:
            work_text.append((ln.y + ln.page * 10000, " ".join(w.text for w in work)))
        name_w = [w for w in ln.words if w.x0 >= geom.name_x0 - 2 and w.xc < geom.unit_x0]
        # tên bị cắt qua ranh giới cột: "Ôtô" | "tự đổ 27 t" → "Ôtô tự đổ 27 t"
        if name_w and work and name_w[0].text[:1].islower() and 0 <= name_w[0].x0 - work[-1].x1 < 6:
            name_w.insert(0, work.pop())
            if work_text and work_text[-1][0] == ln.y + ln.page * 10000:
                work_text[-1] = (work_text[-1][0], " ".join(w.text for w in work))
        unit_w = [w for w in ln.words if geom.unit_x0 <= w.xc <= geom.unit_x1]
        val_w = [w for w in ln.words if w.x0 > geom.unit_x1 - 1]
        name = " ".join(w.text for w in name_w).strip()
        cat = _is_category(name)
        if cat and not unit_w and not val_w:
            kind = cat
            items.append({"y": ln.y + ln.page * 10000, "cat": cat})
            continue
        vals: dict[int, str | None] = {}
        for w in val_w:
            k = col_of(w.xc)
            if k is None:
                continue
            if w.text in DASH:
                vals[k] = None
            else:
                n = _num(w.text)
                if n is not None:
                    vals[k] = n
        items.append(
            {
                "y": ln.y + ln.page * 10000,
                "name": name,
                "unit": " ".join(w.text for w in unit_w),
                "vals": vals,
                "kind": kind,
            }
        )

    # ---- ghép tên xuống dòng
    merged: list[dict] = []
    pending = ""
    for idx, it in enumerate(items):
        if "cat" in it:
            if pending and merged and "cat" not in merged[-1]:
                merged[-1]["name"] += " " + pending
            pending = ""
            merged.append(it)
            continue
        has_vals = bool(it["vals"]) or bool(it["unit"])
        if not has_vals:
            if not it["name"]:
                continue
            nxt = items[idx + 1] if idx + 1 < len(items) else None
            nxt_has_vals = nxt is not None and "cat" not in nxt and (bool(nxt["vals"]) or bool(nxt["unit"]))
            if nxt_has_vals and not nxt["name"]:
                pending = (pending + " " + it["name"]).strip()  # tên ở trên, số liệu ở dòng dưới
            elif merged and "cat" not in merged[-1]:
                merged[-1]["name"] += " " + it["name"]  # phần đuôi tên của dòng trước
            elif nxt_has_vals:
                pending = (pending + " " + it["name"]).strip()
            continue
        if pending:
            it["name"] = (pending + " " + it["name"]).strip()
            pending = ""
        merged.append(it)

    # ---- chia theo mã gốc (một bảng có thể chứa nhiều mã)
    if not codes:
        report.skipped_tables.append(f"p{suffix_line.page}: không thấy mã hiệu trong bảng ({heading_code})")
        return []
    codes.sort()
    # cùng một mã gốc lặp lại trong bảng (vd phần "trên cạn" / "dưới nước") → một nhóm duy nhất
    uniq: list[tuple[float, str, int]] = []
    for c in codes:
        if not any(u[1] == c[1] for u in uniq):
            uniq.append(c)
    if len(uniq) < len(codes) and len({c[1] for c in codes}) == 1:
        codes = uniq
    groups: list[list[dict]] = [[] for _ in codes]
    if len(codes) == 1:
        groups[0] = merged
    else:
        starts = [k for k, it in enumerate(merged) if it.get("cat") == "MATERIAL"]
        if len(starts) == len(codes):
            bounds = starts + [len(merged)]
            for g in range(len(codes)):
                groups[g] = merged[bounds[g] : bounds[g + 1]]
        else:
            # gán theo mã gần nhất phía trên (mã thường nằm ngang dòng đầu nhóm)
            for it in merged:
                g = max([k for k, c in enumerate(codes) if c[0] <= it["y"] + 25] or [0])
                groups[g].append(it)

    appendix = appendix_of_page(suffix_line.page)
    span = " ".join(span_label).strip()
    out: list[NormRecord] = []
    for g, (_cy, base, _pg) in enumerate(codes):
        work = " ".join(
            t
            for (y, t) in work_text
            if (g == 0 or y >= codes[g][0] - 25) and (g + 1 >= len(codes) or y < codes[g + 1][0] - 25)
        )
        work = re.sub(r"\s+", " ", work).strip() or heading_name.capitalize()
        for k, (_, suffix) in enumerate(cols):
            comps: list[Component] = []
            for it in groups[g]:
                if "cat" in it or not it["name"]:
                    continue
                v = it["vals"].get(k)
                if v is None:
                    continue
                name = re.sub(r"\s+", " ", it["name"]).strip()
                unit = it["unit"].strip()
                kd = _kind_for(name, it["kind"])
                other = unit == "%"
                comps.append(Component(kd, name, unit, v, other))
            if not comps:
                continue
            label = " ".join(col_labels[k]).strip()
            parts = [work]
            if span or label:
                parts.append(f"{span} {label}".strip())
            out.append(
                NormRecord(
                    code=_join_code(base, suffix),
                    name=", ".join(p for p in parts if p),
                    unit=unit_of_work,
                    appendix=appendix,
                    group_code=heading_code,
                    group_name=heading_name,
                    page=suffix_line.page,
                    components=comps,
                )
            )
    report.records += len(out)
    return out


def _join_code(base: str, suffix: str) -> str:
    """AF.111 + 10 → AF.11110; AF.1111 + 1 → AF.11111; 14.110 + 01 → 14.11001 (5 chữ số sau dấu chấm)."""
    digits = base.split(".", 1)[1]
    need = 5 - len(digits)
    return base + (suffix.zfill(need) if need > 0 and len(suffix) <= need else suffix)


# --------------------------------------------------------------------------- entry point


def parse_tt38(bbox_html: str) -> tuple[list[NormRecord], ParseReport]:
    report = ParseReport()
    pages = read_pages(bbox_html)
    report.pages = len(pages)
    # xác định phụ lục theo trang bìa "(Phụ lục X kèm theo ..."
    starts: list[tuple[int, str]] = []
    for pno, words in enumerate(pages, 1):
        text = " ".join(w.text for w in words[:80])
        m = re.search(r"\(Phụ lục ([IVX]+) kèm theo", text)
        if m:
            starts.append((pno, m.group(1)))

    def appendix_of_page(p: int) -> str:
        cur = ""
        for sp, ap in starts:
            if p >= sp:
                cur = ap
        return cur

    all_lines: list[Line] = []
    for words in pages:
        body = [w for w in words if 40 < w.y0 < 800]  # bỏ số trang đầu/cuối
        all_lines.extend(to_lines(body))
    records = parse_tables(all_lines, appendix_of_page, report)
    # mã trùng: giữ bản đầu, ghi cảnh báo
    seen: dict[str, NormRecord] = {}
    for r in records:
        if r.code in seen:
            report.warnings.append(f"Trùng mã {r.code} (trang {seen[r.code].page} và {r.page})")
            continue
        seen[r.code] = r
    return list(seen.values()), report
