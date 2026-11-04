"""Safe quantity-expression evaluator.

Grammar: numbers (dot decimal), + - * / unary minus, parentheses, named variables.
No function calls, attributes, power, comparisons. Numbers are parsed from source text
into Decimal (never through float).
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation


class QuantityError(ValueError):
    pass


_BIN = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def evaluate(expr: str, variables: dict[str, Decimal] | None = None) -> Decimal:
    src = (expr or "").strip().replace("×", "*").replace("÷", "/")
    # "2x3" / "2 X 3" between numbers/parentheses → multiplication (common estimator shorthand)
    src = re.sub(r"(?<=[\d\)\s])[xX](?=[\d\(\s])", "*", src)
    if not src:
        raise QuantityError("Công thức rỗng")
    if len(src) > 2000:
        raise QuantityError("Công thức quá dài")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise QuantityError(f"Công thức không hợp lệ: {e.msg}") from e
    variables = variables or {}

    def ev(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise QuantityError("Chỉ cho phép hằng số")
            seg = ast.get_source_segment(src, node) or str(node.value)
            try:
                return Decimal(seg)
            except InvalidOperation as e:
                raise QuantityError(f"Số không hợp lệ: {seg}") from e
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            try:
                return _BIN[type(node.op)](ev(node.left), ev(node.right))
            except (DivisionByZero, ZeroDivisionError, InvalidOperation) as e:
                raise QuantityError("Chia cho 0") from e
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise QuantityError(f"Biến chưa khai báo: {node.id}")
            return Decimal(str(variables[node.id]))
        raise QuantityError(f"Cú pháp không được phép: {type(node).__name__}")

    return ev(tree)


# --------------------------------------------------------------------------- diễn giải khối lượng (nhiều dòng)

DIM_KEYS = ("n", "l", "w", "h")  # số cấu kiện, dài, rộng, cao


def _num(v) -> Decimal | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise QuantityError(f"Số không hợp lệ: {v}") from e


def detail_value(d: dict) -> Decimal | None:
    """Giá trị một dòng diễn giải.

    - có ``expr`` → giá trị công thức, nhân thêm số cấu kiện ``n`` nếu có;
    - không có ``expr`` nhưng có kích thước → tích các ô Số CK × Dài × Rộng × Cao đã nhập;
    - không có gì → dòng ghi chú (None, không cộng vào khối lượng).
    """
    expr = str(d.get("expr") or "").strip()
    dims = {k: _num(d.get(k)) for k in DIM_KEYS}
    if expr:
        v = evaluate(expr)
        return v * dims["n"] if dims["n"] is not None else v
    present = [v for v in dims.values() if v is not None]
    if not present:
        return None
    out = Decimal(1)
    for v in present:
        out *= v
    return out


def sum_details(details: list[dict]) -> tuple[Decimal, list[dict]]:
    """Trả về (tổng khối lượng, danh sách diễn giải đã chuẩn hóa kèm ``value``)."""
    total = Decimal(0)
    out: list[dict] = []
    for i, d in enumerate(details or []):
        if not isinstance(d, dict):
            raise QuantityError(f"Dòng diễn giải {i + 1} không hợp lệ")
        try:
            v = detail_value(d)
        except QuantityError as e:
            raise QuantityError(f"Dòng diễn giải {i + 1}: {e}") from e
        norm = {"text": str(d.get("text") or "")[:500], "expr": str(d.get("expr") or "").strip()[:500]}
        for k in DIM_KEYS:
            n = _num(d.get(k))
            norm[k] = None if n is None else str(n)
        norm["value"] = None if v is None else str(v)
        if v is not None:
            total += v
        out.append(norm)
    return total, out
