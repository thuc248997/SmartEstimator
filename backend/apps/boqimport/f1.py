"""Nạp giá vật tư từ file dự toán xuất bởi phần mềm F1 (sheet "Vật liệu") thành bảng giá tham khảo.

Sheet "Vật liệu" của F1: dòng có STT là một vật tư (Mã hiệu F1, Tên vật tư, Đơn vị, Giá gốc, Giá thông báo,
Giá hiện tại…), các dòng không STT bên dưới là công tác dùng vật tư đó. Lấy "Giá hiện tại" (giá đã dùng để tính),
nếu trống thì "Giá thông báo", rồi "Giá gốc"; bỏ dòng giá 0 và dòng "%".

Kết quả là một DatasetRelease kind=CATALOG với meta.source_kind="estimate" — ưu tiên SAU công bố giá chính thức
của Sở Xây dựng khi tự áp giá, và lý do áp giá luôn ghi rõ "giá tham khảo từ dự toán F1 …".
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from django.db import transaction
from openpyxl import load_workbook

from apps.catalog.models import DatasetRelease
from apps.datasync.models import PriceCatalogItem

from .parser import _key, _text

_HEADERS = {"ma hieu": "code", "ten vat tu": "name", "don vi": "unit", "gia goc": "goc",
            "gia thong bao": "tb", "gia hien tai": "ht"}  # fmt: skip


class F1Error(ValueError):
    pass


def _dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d > 0 else None


def read_f1_materials(data: bytes) -> dict:
    try:
        wb = load_workbook(BytesIO(data), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001
        raise F1Error("Không đọc được file F1 (.xlsx / .xlsm)") from e
    if "Vật liệu" not in wb.sheetnames:
        raise F1Error("File không có sheet “Vật liệu” của F1")
    ws = wb["Vật liệu"]
    rows = list(ws.iter_rows(values_only=True))
    basis = next((_text(r[0]) for r in rows[:5] if r and _key(r[0]).startswith("(can cu")), "")
    hdr_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        keys = [_key(v) for v in r]
        if "ten vat tu" in keys and "gia hien tai" in keys:
            hdr_i = i
            for j, k in enumerate(keys):
                if k in _HEADERS and _HEADERS[k] not in cols:
                    cols[_HEADERS[k]] = j
            break
    if hdr_i is None:
        raise F1Error("Không thấy dòng tiêu đề (Tên vật tư / Giá hiện tại) trong sheet “Vật liệu”")
    items, skipped = [], 0
    for r in rows[hdr_i + 1 :]:
        stt = _text(r[0]) if r else ""
        if not stt.isdigit():
            continue
        name, unit = _text(r[cols["name"]]), _text(r[cols["unit"]])
        price = _dec(r[cols.get("ht")]) or _dec(r[cols.get("tb")]) or _dec(r[cols.get("goc")])
        if not name or not price or unit == "%":
            skipped += 1
            continue
        items.append({"code": _text(r[cols["code"]]), "name": name, "unit": unit, "price": price, "row": stt})
    return {"basis": basis, "items": items, "skipped": skipped}


def _period(basis: str) -> str:
    m = re.search(r"quý\s*(\d)\s*/\s*(\d{4})", basis, re.I)
    return f"{m.group(2)}-Q{m.group(1)}" if m else ""


@transaction.atomic
def import_f1_file(path: Path, label: str, region: str = "Hà Nội") -> tuple[DatasetRelease, dict]:
    data = Path(path).read_bytes()
    parsed = read_f1_materials(data)
    if not parsed["items"]:
        raise F1Error("Sheet “Vật liệu” không có vật tư nào có giá")
    sha = hashlib.sha256(data).hexdigest()
    period = _period(parsed["basis"])
    rel, created = DatasetRelease.objects.get_or_create(
        kind=DatasetRelease.Kind.CATALOG,
        name=f"Giá vật tư tham khảo — dự toán F1 {label}",
        version=sha[:12],
        defaults={
            "region": region,
            "status": DatasetRelease.Status.PUBLISHED,
            "notes": f"Xuất từ phần mềm F1, sheet Vật liệu, cột Giá hiện tại. {parsed['basis']}".strip(),
            "meta": {
                "source_kind": "estimate",
                "software": "F1",
                "file": Path(path).name,
                "sha256": sha,
                "period": period,
                "basis": parsed["basis"],
            },
        },
    )
    if created:
        PriceCatalogItem.objects.bulk_create(
            PriceCatalogItem(
                release=rel,
                name=it["name"][:500],
                unit=it["unit"][:30],
                price=it["price"],
                context=f"F1 {it['code']} · STT {it['row']}"[:500],
                page=0,
                document=Path(path).name[:200],
            )
            for it in parsed["items"]
        )
    return rel, {"created": created, "items": len(parsed["items"]), "skipped": parsed["skipped"], "period": period}
