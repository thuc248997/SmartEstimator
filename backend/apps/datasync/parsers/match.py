"""Ghép tên nguồn lực trong định mức (không có mã) với danh mục giá công bố (máy, nhân công)."""

from __future__ import annotations

import re
import unicodedata

_NOISE = re.compile(r"\bhoặc (loại )?tương tự\b|\bhoặc tương đương\b", re.I)


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    s = _NOISE.sub(" ", s)
    s = s.replace("thuỷ", "thủy").replace("ô tô", "ôtô").replace("ô-tô", "ôtô")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    s = re.sub(r"(\d)\s*(m3|m2|kw|kva|cv|t|tấn|l|lít|lit|mm|m|kg|kn|w|v|a|m3/h|l/h|m3/ph|t/h)\b", r"\1 \2", s)
    s = s.replace("lít", "l").replace("lit", "l").replace("tấn", "t")
    return re.sub(r"[^\w./≤<>]+", " ", s).strip()


def numbers(s: str) -> set[str]:
    return {str(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", s)}


def tokens(s: str) -> set[str]:
    return set(s.split())


LABOR_ALIASES = [
    (re.compile(r"nhóm\s*1\b"), "Nhân công nhóm 1"),
    (re.compile(r"nhóm\s*2\b"), "Nhân công nhóm 2"),
    (re.compile(r"nhóm\s*3\b"), "Nhân công nhóm 3"),
    (re.compile(r"nhóm\s*4\b"), "Nhân công nhóm 4"),
    (re.compile(r"kỹ sư"), "Kỹ sư"),
    (re.compile(r"thợ lặn"), "Thợ lặn"),
    (re.compile(r"nghệ nhân"), "Nghệ nhân"),
    (re.compile(r"lái xe"), "Lái xe"),
    (re.compile(r"thuyền|tàu"), "Nhân công vận hành tàu thuyền"),
]


def canonical_labor(name: str) -> str | None:
    n = name.lower()
    for pat, canon in LABOR_ALIASES:
        if pat.search(n):
            return canon
    return None


class MachineMatcher:
    """Ứng viên hợp lệ: chứa đủ các số (công suất, dung tích…) của tên định mức và các từ chỉ loại máy
    (2 từ đầu). Chọn ứng viên trùng nhiều từ nhất, ít từ thừa nhất."""

    def __init__(self, catalog: list[tuple[str, str]]):  # (code, name)
        self.items = [(code, name, norm_text(name)) for code, name in catalog]
        self.prepared = [(code, name, n, tokens(n), numbers(n)) for code, name, n in self.items]

    def match(self, norm_name: str) -> tuple[str, str, float] | None:
        n = norm_text(norm_name)
        toks = tokens(n)
        nums = numbers(n)
        words = [w for w in n.split() if not re.match(r"^[\d.]+$", w)]
        head = set(words[:2])
        best = None
        for code, name, _pn, ptoks, pnums in self.prepared:
            if not head <= ptoks or not nums <= pnums:
                continue
            overlap = len(toks & ptoks) / max(len(toks), 1)
            extra = len(pnums - nums)
            score = overlap - 0.05 * extra - 0.01 * len(ptoks - toks)
            if best is None or score > best[2]:
                best = (code, name, score)
        if best and best[2] >= 0.5:
            return best
        return None
