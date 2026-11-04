"""Bóc tách bảng giá do Sở Xây dựng Hà Nội công bố (văn bản PDF có lớp chữ, đọc bằng pdftotext -layout).

- Đơn giá nhân công (vd QĐ 2036/QĐ-SXD 26/10/2026): theo nhóm, Vùng I / Vùng II.
- Giá ca máy và thiết bị thi công (vd bảng kèm QĐ 2037/QĐ-SXD): mã M101.0101…, giá ca máy Vùng I / Vùng II.
- Giá vật liệu công bố theo quý: danh mục tham khảo (tên, quy cách, đơn vị, giá, địa điểm/nhà sản xuất).
Thuần Python; mọi giá chưa gồm VAT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PRICE = r"\d{1,3}(?:\.\d{3})+"
PRICE_RE = re.compile(PRICE)


def money(s: str) -> str:
    return s.replace(".", "").replace(",", "")


@dataclass
class DocInfo:
    number: str = ""  # vd "2036/QĐ-SXD"
    issued_on: str = ""  # ISO yyyy-mm-dd
    title: str = ""


def doc_info(text: str) -> DocInfo:
    info = DocInfo()
    m = re.search(r"Số\s*:\s*([0-9.]+)\s*/\s*((?:QĐ|CBGVL)[-–][A-ZĐ\-]+|[A-ZĐ]+[-–][A-ZĐ\-]+)", text)
    if m:
        info.number = f"{m.group(1)}/{m.group(2).replace('–', '-')}"
    m = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", text)
    if m:
        d, mo, y = m.groups()
        info.issued_on = f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"Về việc\s+([^\n]+(?:\n[^\n]+)?)", text)
    if m:
        info.title = re.sub(r"\s+", " ", m.group(1)).strip()
    return info


# --------------------------------------------------------------------------- nhân công

LABOR_KEYS = [
    ("Nhân công nhóm 1", r"Nhóm\s*1\b"),
    ("Nhân công nhóm 2", r"Nhóm\s*2\b"),
    ("Nhân công nhóm 3", r"Nhóm\s*3\b"),
    ("Nhân công nhóm 4", r"Nhóm\s*4\b"),
    ("Nhân công vận hành, điều khiển máy", r"vận hành máy"),
    ("Lái xe", r"Lái xe"),
    ("Nhân công vận hành tàu thuyền", r"tầu thuyền|tàu thuyền|Thuyền trưởng"),
    ("Kỹ sư", r"Kỹ sư"),
    ("Thợ lặn", r"Thợ lặn"),
    ("Nghệ nhân", r"Nghệ nhân"),
]


@dataclass
class LaborPrice:
    name: str
    vung1: str
    vung2: str


def parse_labor(text: str) -> list[LaborPrice]:
    """Các dòng có 2 giá ở cuối, theo thứ tự cố định của bảng (TT 37/2026): nhóm 1–4, vận hành máy, lái xe,
    tàu thuyền, kỹ sư, thợ lặn, nghệ nhân. Kiểm tra chéo nhãn ở vùng lân cận dòng giá."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if re.search(r"Nhóm nhân công xây dựng", ln)), 0)
    price_lines = [
        (i, m) for i, ln in enumerate(lines[start:], start) if (m := re.search(rf"({PRICE})\s+({PRICE})\s*$", ln))
    ]
    out: list[LaborPrice] = []
    for (name, pat), (i, m) in zip(LABOR_KEYS, price_lines, strict=False):
        ctx = "\n".join(lines[max(0, i - 6) : i + 6])
        if not re.search(pat, ctx):
            raise ValueError(f"Bảng nhân công không đúng cấu trúc ở dòng '{lines[i].strip()}' (cần {name})")
        out.append(LaborPrice(name, money(m.group(1)), money(m.group(2))))
    if len(out) < 4:
        raise ValueError("Không đọc được bảng đơn giá nhân công")
    return out


# --------------------------------------------------------------------------- ca máy

CODE_RE = re.compile(r"^\s*(?:\d+[a-z]?\s+)?(M\d{3}\.\d{4}[a-z]?)\b(.*)$")


@dataclass
class MachinePrice:
    code: str
    name: str
    vung1: str
    vung2: str
    fuel: str = ""


def parse_machines(text: str) -> list[MachinePrice]:
    rows: list[dict] = []
    for ln in text.split("\n"):
        if not ln.strip() or "Kèm theo" in ln:
            continue
        m = CODE_RE.match(ln)
        if m:
            code, rest = m.group(1), m.group(2)
            prices = PRICE_RE.findall(rest)
            name = re.split(r"\s{2,}\d", rest.strip(), maxsplit=1)[0].strip()
            name = re.sub(r"\s{2,}.*$", "", name)
            if re.fullmatch(r"[\d\s.,]*", name):
                name = ""
            rows.append({"code": code, "name": name, "prices": prices, "pre": [], "post": []})
        else:
            seg = ln[:48].strip()
            seg = re.sub(r"^\d+[a-z]?\s+", "", seg)  # STT
            if re.search(
                r"Mã hiệu|Định mức|Số ca|Loại máy|Stt|hao chữa|nhiên liệu|lượng \(1ca\)"
                r"|^năm\b|^khác$|^Chi$|^\d+(\s+\d+){3,}",
                seg,
            ):
                continue  # tiêu đề bảng lặp lại ở đầu trang
            if not seg or re.fullmatch(r"[\d\s]+", seg) or (seg.isupper() and len(seg) >= 2):
                continue  # số, mũ, tiêu đề chương/mục viết hoa
            if rows and (seg[:1].islower() or seg[:1] in "(-/,"):
                rows[-1]["post"].append(seg)  # đuôi tên của dòng trên
            else:
                rows.append({"code": None, "pre_text": seg})
    # gộp "tên ở dòng trên" vào mã kế tiếp
    merged: list[dict] = []
    pending: list[str] = []
    for r in rows:
        if r.get("code") is None:
            pending.append(r["pre_text"])
            continue
        r["pre"] = pending
        pending = []
        merged.append(r)
    out: list[MachinePrice] = []
    group = ""
    for r in merged:
        name = " ".join(r["pre"] + ([r["name"]] if r["name"] else []) + r["post"]).strip()
        name = re.sub(r"\s+", " ", name).replace("- -", "-")
        if len(r["prices"]) < 2:
            if name:
                group = re.sub(r"\s*[-–]?\s*$", "", name).rstrip(":").strip()
            continue
        full = f"{group} {name}".strip() if (name[:1].isdigit() or name[:1] in "≤<>") and group else name
        if not full[:1].isdigit():
            pass
        out.append(MachinePrice(r["code"], full, money(r["prices"][-2]), money(r["prices"][-1]), money(r["prices"][0])))
    return out


# --------------------------------------------------------------------------- vật liệu (danh mục tham khảo)

UNITS = (
    "m3",
    "m2",
    "m",
    "md",
    "kg",
    "tấn",
    "tan",
    "viên",
    "vien",
    "cái",
    "bộ",
    "lít",
    "cuộn",
    "tấm",
    "thanh",
    "cây",
    "bao",
    "hộp",
    "thùng",
    "chiếc",
    "lọ",
    "can",
    "km",
    "Kg",
    "Tấn",
    "Viên",
    "Cái",
    "Bộ",
    "Lít",
    "M2",
    "M3",
    "Md",
    "Tấm",
    "Thanh",
    "Cuộn",
    "Bao",
    "Thùng",
    "ống",
    "Ống",
    "m²",
    "m³",
    "đôi",
    "chai",
    "gói",
    "set",
    "Hộp",
)
UNIT_RE = re.compile(r"(?<!\S)(" + "|".join(re.escape(u) for u in UNITS) + r")(?!\S)")


@dataclass
class MaterialPrice:
    name: str
    spec: str
    unit: str
    price: str
    context: str
    page: int
    extra: dict = field(default_factory=dict)


def parse_materials(text: str) -> list[MaterialPrice]:
    out: list[MaterialPrice] = []
    context = ""
    group = ""
    for pno, page in enumerate(text.split("\f"), 1):
        for ln in page.split("\n"):
            s = ln.rstrip()
            if not s.strip():
                continue
            m = re.search(rf"({PRICE}|\d{{1,3}}(?:,\d{{3}})+)\s*$", s)
            if not m:
                t = s.strip()
                if re.match(r"^[IVX]+\s*[-–.]", t):
                    group = t
                    context = ""
                elif len(t) < 120 and not re.search(r"Đơn vị|STT|Công bố|chưa VAT|Kèm theo|Danh mục", t):
                    context = t
                continue
            price = money(m.group(1))
            body = s[: m.start()].rstrip()
            units = list(UNIT_RE.finditer(body))
            um = units[-1] if units else None
            if not um:
                continue
            name = re.sub(r"^\s*\d+\s+", "", body[: um.start()]).strip()
            name = re.sub(r"\s{2,}", " | ", name)
            spec = re.sub(r"\s{2,}", " | ", body[um.end() :].strip())
            if not name or int(price) <= 0:
                continue
            out.append(MaterialPrice(name, spec, um.group(1).lower(), price, f"{group} · {context}".strip(" ·"), pno))
    return out
