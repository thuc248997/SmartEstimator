"""Gợi ý mã định mức cho một dòng BoQ chỉ có tên công tác + đơn vị.

Cách chấm điểm (không dùng dịch vụ ngoài, chạy hoàn toàn trên dữ liệu đã nạp):
1. Văn bản: độ phủ TF-IDF trên âm tiết và cặp âm tiết liền nhau, GIỮ dấu (cáp ≠ cấp ≠ cắt), có mở rộng
   viết tắt hay gặp trong BoQ (BTCT, VK, SXLD…).
2. Đơn vị: định mức có cùng loại đơn vị với BoQ (m3 ↔ 100m3) được giữ điểm; khác loại bị trừ mạnh.
3. Kích thước: "dày 22cm", "cao 3,6m", "rộng 1,2m" trong tên BoQ được so với điều kiện "Chiều dày ≤ 11 (cm)",
   "Chiều cao (m) ≤ 6" trong tên định mức; điều kiện thỏa được cộng điểm, điều kiện sai bị trừ điểm,
   cùng điểm thì ưu tiên khoảng chặt hơn.
Kết quả chỉ là GỢI Ý: dòng có độ tin cậy thấp phải được người lập dự toán chọn lại.
"""

from __future__ import annotations

import math
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from apps.catalog.models import WorkItem

from .units import conversion_factor, strip_accents

# Viết tắt hay gặp trong BoQ (khóa không dấu) → cụm có dấu
ABBREV = {
    "btct": "bê tông cốt thép",
    "bt": "bê tông",
    "btl": "bê tông lót",
    "vk": "ván khuôn",
    "sxld": "sản xuất lắp dựng",
    "sx": "sản xuất",
    "ld": "lắp dựng",
    "gcld": "gia công lắp dựng",
    "tp": "thành phẩm",
    "kc": "kết cấu",
    "pccc": "phòng cháy chữa cháy",
}

_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+")
# Từ nối không mang nghĩa phân biệt (dạng không dấu; so cả bản có dấu sau khi bỏ dấu).
# Không đưa "trong" vào đây: "tường trong" ≠ "tường ngoài".
_STOP_PLAIN = {
    "chieu",
    "cong",
    "tac",
    "va",
    "cac",
    "loai",
    "bang",
    "cho",
    "theo",
    "tai",
    "voi",
    "co",
    "the",
    "de",
    "la",
}
_STOP_ACC = {"chiều", "công", "tác", "và", "các", "loại", "bằng", "cho", "theo", "tại", "với", "có", "thể", "để", "là"}

# Kiểu bỏ dấu cũ ("hoà", "thuỷ") → kiểu mới ("hòa", "thủy") để hai cách viết khớp nhau
_OLD_TONE = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}  # fmt: skip
_OLD_TONE_RE = re.compile("|".join(_OLD_TONE))


def lower_vn(text: str) -> str:
    """Chữ thường, NFC, thống nhất kiểu bỏ dấu, ≤ ≥ → <= >= — GIỮ dấu tiếng Việt."""
    s = unicodedata.normalize("NFC", text or "").lower()
    s = _OLD_TONE_RE.sub(lambda m: _OLD_TONE[m.group(0)], s)
    return s.replace("≤", " <= ").replace("≥", " >= ")


def normalize(text: str) -> str:
    """Bản không dấu (dùng cho so kích thước, khóa ghi nhớ, và khi BoQ viết không dấu)."""
    return strip_accents(lower_vn(text))


def has_diacritics(text: str) -> bool:
    s = lower_vn(text)
    return s != strip_accents(s)


def _num_token(t: str) -> str:
    d = Decimal(t.replace(",", "."))
    return format(d.normalize(), "f") if d == d.to_integral_value() or "." in t or "," in t else t


# Quy cách vật liệu nằm trong thành phần hao phí chứ không nằm trong tên định mức → bỏ khi so tên
_MATERIAL_SPEC = re.compile(
    r"\b(?:da\s*\d+\s*x\s*\d+|mac\s*\d+|m\s?\d{3}\b|b\d{2}\b|vxm\s*(?:mac\s*)?\d+|"
    r"vua\s+(?:xi\s+mang|xm|tam\s+hop|vxm)?\s*(?:mac\s*)?\d*|pcb\s*\d+)"
)


def strip_specs(text: str) -> str:
    """Xóa quy cách vật liệu, giữ nguyên dấu phần còn lại (bản không dấu cùng độ dài để dò vị trí)."""
    s = lower_vn(text)
    plain = "".join(strip_accents(c) or c for c in s)
    if len(plain) != len(s):
        return _MATERIAL_SPEC.sub(" ", plain)
    out = list(s)
    for m in _MATERIAL_SPEC.finditer(plain):
        out[m.start() : m.end()] = " " * (m.end() - m.start())
    return "".join(out)


def tokens(text: str, accented: bool = True) -> list[str]:
    s = lower_vn(text)
    if not accented:
        s = strip_accents(s)
    out: list[str] = []
    for t in _TOKEN.findall(s):
        if t[0].isdigit():
            out.append(_num_token(t))
            continue
        exp = ABBREV.get(strip_accents(t))
        if exp and t == strip_accents(t):
            out.extend((exp if accented else strip_accents(exp)).split())
        else:
            out.append(t)
    return out


_UNIT_WORDS = {"mm", "cm", "m", "m2", "m3", "kg", "t"}


def features(text: str, accented: bool = True) -> Counter:
    """Âm tiết + cặp âm tiết liền nhau. Số đo và đơn vị đo chỉ giữ dạng âm tiết đơn (trọng số thấp),
    vì kích thước đã được so riêng theo điều kiện ≤ / > ở bước sau."""
    stop = _STOP_ACC if accented else _STOP_PLAIN
    words = [t for t in tokens(text, accented) if t not in stop and t not in _UNIT_WORDS]
    f: Counter = Counter()
    for w in words:
        f[w] += 0.5 if w[0].isdigit() else 1.0
    for a, b in zip(words, words[1:], strict=False):
        if not (a[0].isdigit() or b[0].isdigit()):
            f[f"{a}_{b}"] += 1.5
    return f


# ----------------------------------------------------------------------------- kích thước
_KW = {
    "day": "day",
    "cao": "cao",
    "rong": "rong",
    "sau": "sau",
    "kinh": "kinh",
    "phi": "kinh",
    "d": "kinh",
    "dai": "dai",
}
_DEFAULT_UNIT = {"day": "cm", "rong": "cm", "cao": "m", "sau": "m", "kinh": "mm", "dai": "m"}
_TO_M = {"mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal(1)}

_COND = re.compile(
    r"\b(day|cao|rong|sau|kinh|dai)\b[^0-9<>=]{0,25}?(?:\((mm|cm|m)\))?\s*(<=|>=|<|>)?\s*(\d+(?:[.,]\d+)?)"
    r"\s*(?:\(?(mm|cm|m)\b\)?)?"
)
_QDIM = re.compile(
    r"\b(day|cao|rong|sau|kinh|phi|dai|d)\s*(<=|>=|<|>|=|:)?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?(?![a-z0-9])"
)


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def candidate_conditions(name: str) -> list[tuple[str, str, Decimal]]:
    """[(kích thước, toán tử, giá trị theo mét)] trích từ tên định mức."""
    out = []
    for kw, unit_before, op, val, unit_after in _COND.findall(normalize(name)):
        unit = unit_before or unit_after or _DEFAULT_UNIT[kw]
        out.append((kw, op or "=", _dec(val) * _TO_M[unit]))
    return out


def query_dimensions(name: str) -> dict[str, Decimal]:
    """{kích thước: giá trị theo mét} trích từ tên BoQ: "tường dày 220" → day=0.22."""
    out: dict[str, Decimal] = {}
    for kw, op, val, unit in _QDIM.findall(normalize(name)):
        k = _KW[kw]
        v = _dec(val)
        if not unit:
            if k == "kinh":
                unit = "mm"
            elif k in ("day", "rong"):
                unit = "mm" if v >= 50 else ("m" if v < 1 else "cm")
            else:
                unit = "cm" if v >= 50 else "m"
        x = v * _TO_M[unit]
        # "d>18mm" → một giá trị nằm ngay trên 18 mm; "cao ≤6m" → lấy đúng cận 6 m
        if op in (">", ">="):
            x += _TO_M[unit] * Decimal("0.001")
        out.setdefault(k, x)
    return out


def _check(op: str, x: Decimal, bound: Decimal) -> bool:
    if op == "=":
        return abs(x - bound) <= bound * Decimal("0.02")
    return {"<=": x <= bound, "<": x < bound, ">=": x >= bound, ">": x > bound}[op]


# ----------------------------------------------------------------------------- index
@dataclass
class _Doc:
    id: int
    code: str
    name: str
    unit: str
    conds: list[tuple[str, str, Decimal]]
    group: str = ""
    ref: str = ""


@dataclass
class _Space:
    """Không gian đặc trưng: có dấu (mặc định) hoặc không dấu (khi BoQ viết không dấu)."""

    vecs: list[dict[str, float]] = field(default_factory=list)
    idf: dict[str, float] = field(default_factory=dict)
    postings: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class _Index:
    docs: list[_Doc] = field(default_factory=list)
    acc: _Space = field(default_factory=_Space)
    plain: _Space = field(default_factory=_Space)
    by_code: dict[str, _Doc] = field(default_factory=dict)
    pos: dict[int, int] = field(default_factory=dict)  # work_item id → vị trí trong docs


_cache: dict[tuple[int, int], _Index] = {}
_GROUP = re.compile(r"nhóm:\s*(.+)$", re.I)
_REF = re.compile(r"^(Phụ lục [IVXLC]+\s*—\s*trang \d+)")


def _group(notes: str) -> tuple[str, str]:
    """notes "Phụ lục II — trang 175 PDF; nhóm: CHIỀU RỘNG MÓNG ≤ 6M" → (nhóm, "Phụ lục II — trang 175")."""
    notes = notes or ""
    g = _GROUP.search(notes)
    r = _REF.search(notes)
    return (g.group(1).strip() if g else ""), (r.group(1) if r else "")


_lock = threading.Lock()


def _space(feats: list[Counter]) -> _Space:
    df: Counter = Counter()
    for f in feats:
        df.update(f.keys())
    n = max(len(feats), 1)
    sp = _Space()
    sp.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    for i, f in enumerate(feats):
        vec = {t: w * sp.idf[t] for t, w in f.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vec = {t: v / norm for t, v in vec.items()}
        sp.vecs.append(vec)
        for t in vec:
            sp.postings[t].append(i)
    return sp


def _doc_features(name: str, group: str, accented: bool) -> Counter:
    f = features(name, accented)
    # Tên nhóm (vd "ĐÀO MÓNG BĂNG", "CHIỀU RỘNG MÓNG ≤ 6M") phân biệt các mã trùng tên → trọng số thấp hơn tên
    for t, w in features(group, accented).items():
        f[t] += 0.5 * w
    return f


def _build(release_id: int) -> _Index:
    rows = list(WorkItem.objects.filter(release_id=release_id).values_list("id", "code", "name", "unit", "notes"))
    key = (release_id, len(rows))
    with _lock:
        if key in _cache:
            return _cache[key]
    groups = [_group(notes) for *_, notes in rows]
    idx = _Index()
    idx.acc = _space([_doc_features(r[2], g, True) for r, (g, _) in zip(rows, groups, strict=True)])
    idx.plain = _space([_doc_features(r[2], g, False) for r, (g, _) in zip(rows, groups, strict=True)])
    for (wid, code, name, unit, _), (group, ref) in zip(rows, groups, strict=True):
        doc = _Doc(wid, code, name, unit, candidate_conditions(f"{name} {group}"), group, ref)
        idx.pos[wid] = len(idx.docs)
        idx.docs.append(doc)
        idx.by_code[code.upper()] = doc
    with _lock:
        for k in [k for k in _cache if k[0] == release_id]:
            del _cache[k]
        _cache[key] = idx
    return idx


def get_index(release_id: int) -> _Index:
    n = WorkItem.objects.filter(release_id=release_id).count()
    return _cache.get((release_id, n)) or _build(release_id)


@dataclass
class Candidate:
    work_item: int
    code: str
    name: str
    unit: str
    score: float
    factor: Decimal | None  # khối lượng định mức = KL BoQ × factor
    reasons: list[str]
    group: str = ""
    ref: str = ""
    coverage: float = 1.0  # tỷ lệ âm tiết (không tính số) của tên BoQ có mặt trong tên/nhóm định mức

    def as_dict(self) -> dict:
        return {
            "work_item": self.work_item,
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "score": round(self.score, 3),
            "factor": None if self.factor is None else str(self.factor),
            "reasons": self.reasons,
            "group": self.group,
            "ref": self.ref,
            "coverage": round(self.coverage, 2),
        }


def find_code(idx: _Index, code: str) -> _Doc | None:
    return idx.by_code.get((code or "").strip().upper())


def to_candidate(doc: _Doc, unit: str, score: float = 1.0, reasons: list[str] | None = None) -> Candidate:
    factor = conversion_factor(unit, doc.unit)
    return Candidate(doc.id, doc.code, doc.name, doc.unit, score, factor, reasons or [], doc.group, doc.ref)


_ROMAN = {"i", "ii", "iii", "iv", "v", "vi"}
_REPAIR_HINT = re.compile(r"\b(sua chua|pha do|thao do|cao bo|bao duong|duy tu)\b")


def suggest(idx: _Index, name: str, unit: str, limit: int = 8) -> list[Candidate]:
    # BoQ có dấu → so có dấu ("cáp" ≠ "cấp" ≠ "cắt"); BoQ gõ không dấu → so không dấu
    accented = has_diacritics(name)
    sp = idx.acc if accented else idx.plain
    q = features(strip_specs(name), accented)
    repair = bool(_REPAIR_HINT.search(normalize(name)))
    qvec = {t: w * sp.idf[t] for t, w in q.items() if t in sp.idf}
    qn = math.sqrt(sum(v * v for v in qvec.values()))
    if not qn:
        return []
    # Điểm = 75% "BoQ được phủ bao nhiêu" (tổng trọng số IDF của đặc trưng BoQ có trong tên định mức)
    #      + 25% cosine (phạt tên định mức có nhiều chữ thừa không liên quan).
    qtotal = sum(qvec.values())
    cover: dict[int, float] = defaultdict(float)
    cosine: dict[int, float] = defaultdict(float)
    for t, w in qvec.items():
        for i in sp.postings.get(t, ()):
            cover[i] += w / qtotal
            cosine[i] += (w / qn) * sp.vecs[i][t]
    if not cover:
        return []
    scores = {i: 0.75 * cover[i] + 0.25 * cosine[i] for i in cover}
    # Chỉ xét kỹ nhóm dẫn đầu (đủ rộng để chứa các biến thể khoảng kích thước)
    pool = sorted(scores.items(), key=lambda kv: -kv[1])[:200]
    dims = query_dimensions(name)
    qwords = {t for t in q if "_" not in t and not t[0].isdigit()}
    # Cấp đất / cấp đá / cấp địa hình ghi bằng số La Mã: "cấp II" ≠ "cấp III"
    qroman = qwords & _ROMAN
    ranked = []
    for i, text_score in pool:
        doc = idx.docs[i]
        reasons: list[str] = []
        s = text_score
        factor = conversion_factor(unit, doc.unit) if unit else None
        if unit and factor is None:
            s *= 0.55
            reasons.append(f"đơn vị khác loại ({unit} ↔ {doc.unit})")
        if doc.code[:1] == "S" and not repair:
            s *= 0.85  # Phụ lục VI (sửa chữa, bảo dưỡng): chỉ ưu tiên khi BoQ nói rõ là sửa chữa
        tight = Decimal(0)
        for kw, op, bound in doc.conds:
            if kw not in dims:
                continue
            if _check(op, dims[kw], bound):
                s += 0.06
                if op in ("<=", "<"):
                    tight += bound
            else:
                s -= 0.12
                reasons.append(f"sai điều kiện {kw} {op} {bound.normalize()} m")
        if qroman:
            droman = sp.vecs[i].keys() & _ROMAN
            if droman and not (qroman & droman):
                s -= 0.15
                reasons.append(f"khác cấp ({', '.join(sorted(droman)).upper()})")
        cov = len(qwords & sp.vecs[i].keys()) / len(qwords) if qwords else 1.0
        ranked.append((s, tight if tight else Decimal("1e9"), doc, factor, reasons, cov))
    # Cùng điểm → khoảng chặt hơn (bound nhỏ hơn) đứng trước, rồi theo mã
    ranked.sort(key=lambda r: (-round(r[0], 4), r[1], r[2].code))
    return [
        Candidate(d.id, d.code, d.name, d.unit, s, f, rs, d.group, d.ref, cov) for s, _, d, f, rs, cov in ranked[:limit]
    ]


# ----------------------------------------------------------------------------- loại dòng BoQ
# Động từ mở đầu tên công tác xây lắp (dạng không dấu). Dòng không bắt đầu bằng động từ thường là tên
# thiết bị / vật tư ("Loa âm trần", "Cáp Cat6") → thử thêm "Lắp đặt …" / "Kéo rải …" khi tìm mã.
WORK_VERBS = (
    "lap", "dao", "dap", "xay", "trat", "be tong", "van khuon", "cot thep", "son", "lat", "op", "lang", "keo",
    "rai", "do ", "khoan", "lop", "van chuyen", "thao", "pha", "gia cong", "san xuat", "dong", "ep", "quet", "ba ",
    "cang", "thi cong", "lam", "dat", "chong", "lap", "san ", "cat", "han", "noi", "bom", "tuoi", "trong cay",
    "phun", "cao", "duc", "mai", "danh", "cai dat", "do kiem", "thi nghiem", "kiem tra", "hieu chinh",
    "chay thu", "van hanh", "ve sinh", "xu ly", "boc", "cuon", "tram", "gia co", "be ", "ket noi", "luon",
)  # fmt: skip
_COUNT_UNITS = re.compile(
    r"^(1\s*)?(cai|chiec|bo|tu|con|thiet bi|may|module|cum|hop|dau|he|ht|he thong|soi|thanh|cuon|tam|chuong|ong)\b"
)
# Từ chung chung đứng đầu tên thiết bị, không dùng làm "danh từ chính"
_GENERIC_HEAD = {"bo", "thiet", "bi", "he", "thong", "cai", "chiec", "loai"}
_AMBIGUOUS_HEAD = {"dau", "o", "tu", "hop", "cap", "day", "ong", "thanh", "may", "man", "thiet", "dinh", "he"}
_LUMP_UNITS = re.compile(r"^(goi|tron goi|lo|ht|he thong|khoan|lan|dot|lot)$")
_CABLE = re.compile(r"\b(cap|day|ong|mang|thang cap|day nhay)\b")


def is_work_phrase(name: str) -> bool:
    n = normalize(name).strip()
    return any(n.startswith(v if v.endswith(" ") else v + " ") or n == v.strip() for v in WORK_VERBS)


def line_kind(name: str, unit: str) -> str:
    """work (công tác xây lắp) / equipment (thiết bị: chi phí thiết bị + công lắp đặt) / lump (khoản trọn gói)."""
    u = normalize(unit).strip()
    if _LUMP_UNITS.match(u):
        return "lump"
    if not is_work_phrase(name) and _COUNT_UNITS.match(u):
        return "equipment"
    return "work"


def suggest_best(idx: _Index, name: str, unit: str, kind: str = "work", limit: int = 8) -> list[Candidate]:
    """Gợi ý mã; với tên thiết bị / vật tư (không có động từ) thử thêm "Lắp đặt …" và "Kéo rải …" (cáp, dây),
    lấy điểm cao nhất của mỗi mã. kind=equipment → chỉ tìm định mức lắp đặt."""
    prefix_lap, prefix_keo = ("lắp đặt", "kéo rải") if has_diacritics(name) else ("lap dat", "keo rai")
    if kind == "equipment":
        queries = [f"{prefix_lap} {name}"]
    elif is_work_phrase(name):
        queries = [name]
    else:
        queries = [name, f"{prefix_lap} {name}"]
        if _CABLE.search(normalize(name)):
            queries.append(f"{prefix_keo} {name}")
    best: dict[int, Candidate] = {}
    for q in queries:
        for c in suggest(idx, q, unit, limit=max(limit * 5, 40)):
            if c.work_item not in best or c.score > best[c.work_item].score:
                best[c.work_item] = c
    # Độ phủ tính trên tên GỐC (không tính chữ "lắp đặt" thêm vào) và bắt buộc có danh từ chính:
    # "Loa âm trần" không được khớp "Lắp máy điều hoà âm trần" chỉ vì chung "âm trần".
    accented = has_diacritics(name)
    sp = idx.acc if accented else idx.plain
    words = [t for t in tokens(strip_specs(name), accented) if not t[0].isdigit()]
    stop = _STOP_ACC if accented else _STOP_PLAIN
    content = {t for t in words if t not in stop and t not in _UNIT_WORDS}
    content_seq = [t for t in words if t not in stop and t not in _UNIT_WORDS]
    hi = next((i for i, t in enumerate(content_seq) if strip_accents(t) not in _GENERIC_HEAD), None)
    head = content_seq[hi] if hi is not None else None
    head2 = f"{head}_{content_seq[hi + 1]}" if head and hi + 1 < len(content_seq) else None
    named = not is_work_phrase(name)
    for c in best.values():
        keys = sp.vecs[idx.pos[c.work_item]].keys()
        c.coverage = len(content & keys) / len(content) if content else 1.0
        if not (named and head):
            continue
        # Tên thiết bị / vật tư: mô tả quy cách dài nên chỉ đòi danh từ chính ("camera", "ổ cắm", "tủ điện").
        # Danh từ quá chung ("tủ", "cáp", "ống", "đầu") thì phải khớp cả cụm 2 âm tiết.
        if (head2 and head2 in keys) or (head in keys and strip_accents(head) not in _AMBIGUOUS_HEAD):
            c.coverage = max(c.coverage, 0.6)
            # Biến thể cụ thể của nhóm ("…, Camera" so với "…, Monitor"): phần sau dấu phẩy cuối nói tới danh từ chính
            tail = c.name.rsplit(",", 1)[-1]
            if head in features(tail, accented):
                c.score += 0.05
        else:
            c.coverage = min(c.coverage, 0.5)
            c.reasons.append(f"định mức không nói tới “{(head2 or head).replace('_', ' ')}”")
    # Tên thiết bị: đưa mã có danh từ chính lên trước; tên công tác: giữ thứ tự theo điểm
    out = sorted(
        best.values(),
        key=lambda c: (named and c.coverage < 0.6, -round(c.score * (0.5 + c.coverage / 2), 4), c.code),
    )
    return out[:limit]


def confidence(cands: list[Candidate]) -> str:
    """high / medium / low.

    - high: tên BoQ gần như nằm trọn trong tên định mức, đơn vị quy đổi được, bỏ xa phương án thứ hai;
    - medium: khớp phần lớn nhưng còn các mã gần giống (khác khoảng kích thước, khác chương) → nên xem lại;
    - low: thiếu nhiều từ khóa hoặc đơn vị không quy đổi được → không tự chọn.
    """
    if not cands:
        return "low"
    top = cands[0]
    if top.factor is None or top.coverage < 0.6:
        return "low"
    second = cands[1].score if len(cands) > 1 else 0.0
    if top.coverage >= 0.85 and top.score >= 0.8 and top.score - second >= 0.05:
        return "high"
    return "medium"
