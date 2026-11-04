"""Đọc số tiền bằng chữ tiếng Việt (vd dòng "Bằng chữ" ở bảng tổng hợp)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_SCALES = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ", "tỷ tỷ"]


def _group(n: int, full: bool) -> str:
    h, t, u = n // 100, (n // 10) % 10, n % 10
    words: list[str] = []
    if h or full:
        words += [_DIGITS[h], "trăm"]
    if t == 0:
        if u:
            if h or full:
                words.append("linh")
            words.append(_DIGITS[u])
    elif t == 1:
        words.append("mười")
        if u == 5:
            words.append("lăm")
        elif u:
            words.append(_DIGITS[u])
    else:
        words += [_DIGITS[t], "mươi"]
        if u == 1:
            words.append("mốt")
        elif u == 4:
            words.append("tư")
        elif u == 5:
            words.append("lăm")
        elif u:
            words.append(_DIGITS[u])
    return " ".join(words)


def number_to_words(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + number_to_words(-n)
    groups: list[int] = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    if len(groups) > len(_SCALES):
        raise ValueError("Số quá lớn")
    parts: list[str] = []
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        parts.append(_group(g, full=i != top))
        if _SCALES[i]:
            parts.append(_SCALES[i])
    return " ".join(parts)


def vnd_in_words(amount) -> str:
    n = int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    s = number_to_words(n)
    return s[:1].upper() + s[1:] + " đồng"
