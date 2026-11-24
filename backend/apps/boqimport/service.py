"""Nhập BoQ: xem trước (đọc file + gợi ý mã) và ghi vào dự toán (tạo hạng mục, dòng công tác, tính lại)."""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Max
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.catalog.models import NormComponent, Resource, WorkItem
from apps.projects.models import EquipmentCost, EstimateLine, EstimateRevision, ProjectItem, ResourceOverride
from apps.projects.serializers import EstimateLineSerializer

from . import matcher
from .models import BoqMatchMemory
from .parser import ParsedBoq
from .units import conversion_factor, parse_unit

MAX_LINES = 3000
_DEFAULT_ITEM = re.compile(r"^Hạng mục \d+$")


def memory_key(name: str) -> str:
    return re.sub(r"\s+", " ", matcher.normalize(name)).strip()[:500]


def _fmt(d: Decimal | None) -> str | None:
    if d is None:
        return None
    return format(d.normalize(), "f") if d == d.to_integral_value() else format(d, "f").rstrip("0").rstrip(".")


def build_preview(parsed: ParsedBoq, release_id: int) -> dict:
    idx = matcher.get_index(release_id)
    memory = {
        (m.key, m.unit_base): m.work_item_id
        for m in BoqMatchMemory.objects.filter(release_id=release_id).only("key", "unit_base", "work_item_id")
    }
    docs_by_id = {d.id: d for d in idx.docs}
    stats = {"lines": 0, "code": 0, "memory": 0, "high": 0, "medium": 0, "low": 0, "equipment": 0, "lump": 0}
    items = []
    for it in parsed.items:
        rows = []
        for ln in it.lines:
            stats["lines"] += 1
            doc = matcher.find_code(idx, ln.code) if ln.code else None
            kind = "work" if doc is not None else matcher.line_kind(ln.name, ln.unit)
            stats[kind] = stats.get(kind, 0) + 1
            cands = matcher.suggest_best(idx, ln.name, ln.unit, kind)
            selected = None
            source = "match"
            conf = matcher.confidence(cands)
            mem_id = memory.get((memory_key(ln.name), parse_unit(ln.unit).base))
            if doc is not None:
                selected, source, conf = (
                    matcher.to_candidate(doc, ln.unit, 1.0, ["mã có sẵn trong file"]),
                    "code",
                    "high",
                )
            elif mem_id and mem_id in docs_by_id:
                selected = matcher.to_candidate(docs_by_id[mem_id], ln.unit, 1.0, ["đã chọn ở lần nhập trước"])
                source, conf = "memory", "high"
            elif cands and conf in ("high", "medium") and kind != "lump":
                selected = cands[0]
            if selected is not None and all(c.work_item != selected.work_item for c in cands):
                cands = [selected, *cands[:-1]] if len(cands) >= 8 else [selected, *cands]
            stats[source if source in ("code", "memory") else conf] += 1
            warnings = list(ln.warnings)
            if kind == "lump":
                warnings.append("Khoản trọn gói — sẽ nhập thành dòng tạm tính, cần nhập đơn giá")
            if ln.code and doc is None:
                warnings.append(f"Mã “{ln.code}” trong file không có trong bộ định mức đang dùng")
            rows.append(
                {
                    "row": ln.row,
                    "stt": ln.stt,
                    "code_in_file": ln.code,
                    "name": ln.name,
                    "unit": ln.unit,
                    "quantity": _fmt(ln.quantity),
                    "details": ln.details,
                    "warnings": warnings,
                    "candidates": [c.as_dict() for c in cands],
                    "selected": selected.as_dict() if selected else None,
                    "confidence": conf,
                    "source": source,
                    "kind": kind,
                }
            )
        items.append({"row": it.row, "name": it.name, "lines": rows})
    return {
        "sheets": parsed.sheets,
        "sheet": parsed.sheet,
        "header_row": parsed.header_row,
        "columns": parsed.columns,
        "headers": parsed.headers,
        "items": items,
        "skipped": parsed.skipped,
        "warnings": parsed.warnings,
        "stats": stats,
    }


def _qty_expr(base: str, factor: Decimal) -> str:
    """ "45" × 0,01 → "45/100" (dễ đọc, giống cách kỹ sư ghi); hệ số khác → nhân trực tiếp."""
    if factor == 1:
        return base
    inv = 1 / factor
    if inv == inv.to_integral_value():
        return f"({base})/{int(inv)}" if not re.fullmatch(r"[\d.]+", base) else f"{base}/{int(inv)}"
    return f"({base})*{_fmt(factor)}" if not re.fullmatch(r"[\d.]+", base) else f"{base}*{_fmt(factor)}"


def _zero_equipment_materials(revision: EstimateRevision, wi_ids: set[int], user) -> list[str]:
    """Định mức lắp đặt nhiều khi liệt kê chính thiết bị làm vật liệu (vd "Lắp ổ cắm" có "Ổ cắm 1 cái",
    "Lắp tủ điện" có "Tủ điện 1 bộ"). Thiết bị đã nằm ở Chi phí thiết bị → đặt giá riêng 0 đ cho vật liệu đó
    (có ghi lý do) để không tính hai lần."""
    if not wi_ids:
        return []
    names = []
    done = set(revision.overrides.values_list("resource_id", flat=True))
    for c in NormComponent.objects.filter(
        work_item_id__in=wi_ids, kind=Resource.Kind.MATERIAL, resource__isnull=False, is_other_pct=False
    ).select_related("resource"):
        r = c.resource
        if r.id in done or parse_unit(r.unit).base != "cai" or not (Decimal("0.95") <= c.quantity <= Decimal("1.05")):
            continue
        ResourceOverride.objects.create(
            revision=revision,
            resource=r,
            price=0,
            reason="Là thiết bị chính của công tác lắp đặt, đã tính ở sheet Chi phí thiết bị (nhập BoQ)",
            created_by=user,
        )
        done.add(r.id)
        names.append(r.name)
    return names


@transaction.atomic
def commit(revision: EstimateRevision, payload: dict, user) -> dict:
    if revision.is_locked:
        raise ValidationError({"detail": f"Revision đã {revision.status}, không được sửa. Tạo revision mới."})
    items_in = payload.get("items")
    if not isinstance(items_in, list) or not items_in:
        raise ValidationError({"items": "Không có hạng mục nào để nhập"})
    n_lines = sum(len(it.get("lines") or []) for it in items_in if isinstance(it, dict))
    if n_lines == 0:
        raise ValidationError({"items": "Không có dòng công tác nào được chọn để nhập"})
    if n_lines > MAX_LINES:
        raise ValidationError({"items": f"Tối đa {MAX_LINES} dòng mỗi lần nhập"})

    release_id = revision.project.norm_release_id
    wi_ids = {ln.get("work_item") for it in items_in for ln in it.get("lines") or [] if ln.get("work_item")}
    work_items = {w.id: w for w in WorkItem.objects.filter(pk__in=wi_ids, release_id=release_id)}
    if len(work_items) != len(wi_ids):
        raise ValidationError({"items": "Có mã định mức không thuộc bộ định mức của công trình"})

    # Bỏ hạng mục mặc định rỗng ("Hạng mục 1") do giao diện tạo sẵn
    removed = 0
    for it in revision.items.all():
        if _DEFAULT_ITEM.match(it.name) and not it.lines.exists():
            it.delete()
            removed += 1

    order0 = revision.items.aggregate(m=Max("order"))["m"] or 0
    custom_seq = EstimateLine.objects.filter(item__revision=revision, custom_code__startswith="TT.").count()
    errors = []
    created_items = 0
    lines_payload: list[dict] = []
    stats = {
        "matched": 0,
        "custom": 0,
        "converted": 0,
        "equipment": 0,
        "install_lines": 0,
        "equipment_unpriced": 0,
        "equipment_existing": 0,
    }
    eq_order = revision.equipment.aggregate(m=Max("order"))["m"] or 0
    existing_eq = list(revision.equipment.filter(note__startswith="BoQ"))
    install_wis: set[int] = set()
    memories: list[tuple[str, str, int]] = []
    for i, it in enumerate(items_in, 1):
        name = str(it.get("name") or f"Hạng mục {i}").strip()[:300]
        item = ProjectItem.objects.create(revision=revision, order=order0 + i, name=name)
        created_items += 1
        j = 0
        for ln in it.get("lines") or []:
            kind = ln.get("kind") or "work"
            bname = str(ln.get("name") or "").strip()
            bunit = str(ln.get("unit") or "").strip()
            qty = ln.get("quantity")
            try:
                qty_d = Decimal(str(qty)) if qty not in (None, "") else Decimal(0)
            except Exception:  # noqa: BLE001
                errors.append(f"{bname[:40]}: khối lượng “{qty}” không hợp lệ")
                continue
            details = [d for d in (ln.get("details") or []) if isinstance(d, dict)]
            row = ln.get("row")
            note = f"BoQ{f' dòng {row}' if row else ''}: {bname} — {_fmt(qty_d)} {bunit}"[:500]
            wi = work_items.get(ln.get("work_item")) if ln.get("work_item") else None
            if kind == "equipment":
                # Thiết bị → sheet Chi phí thiết bị (giá theo báo giá); công lắp đặt (nếu chọn mã) → dòng tiên lượng
                try:
                    price = Decimal(str(ln.get("unit_price"))) if ln.get("unit_price") not in (None, "") else None
                except Exception:  # noqa: BLE001
                    errors.append(f"{bname[:40]}: đơn giá thiết bị “{ln.get('unit_price')}” không hợp lệ")
                    continue
                eq_name = f"{bname} [{name}]"[:500] if name else bname[:500]
                eq_qty = qty_d.quantize(Decimal("0.001"))
                # Nhập lại cùng file: thiết bị đã có (cùng tên + hạng mục, đơn vị, số lượng) → không thêm lần nữa;
                # nếu lần này có đơn giá mà dòng cũ chưa có thì cập nhật giá
                existing = next(
                    (e for e in existing_eq if (e.name, e.unit, e.quantity) == (eq_name, bunit[:30], eq_qty)), None
                )
                if existing is not None:
                    existing_eq.remove(existing)
                    if price and not existing.unit_price:
                        EquipmentCost.objects.filter(pk=existing.pk).update(unit_price=price)
                    stats["equipment_existing"] += 1
                else:
                    if price is None or price < 0:
                        stats["equipment_unpriced"] += 1
                    eq_order += 1
                    EquipmentCost.objects.create(
                        revision=revision,
                        order=eq_order,
                        name=eq_name,
                        unit=bunit[:30],
                        quantity=eq_qty,
                        unit_price=price if price is not None and price >= 0 else Decimal(0),
                        note=(f"BoQ dòng {row}" if row else "BoQ")
                        + ("" if price else " — chưa có đơn giá, nhập theo báo giá"),
                    )
                    stats["equipment"] += 1
                if wi is None:
                    continue
                note = f"Công lắp đặt thiết bị — {note}"[:500]
            j += 1
            data = {"item": item.id, "order": j, "note": note}
            if wi is not None:
                factor = conversion_factor(bunit, wi.unit)
                if factor is None:
                    try:
                        factor = Decimal(str(ln.get("factor"))) if ln.get("factor") not in (None, "") else None
                    except Exception:  # noqa: BLE001
                        factor = None
                if factor is None or factor <= 0:
                    errors.append(
                        f"“{bname[:40]}”: đơn vị BoQ “{bunit}” không quy đổi được sang “{wi.unit}” của {wi.code}; "
                        "nhập hệ số quy đổi"
                    )
                    continue
                data.update(work_item=wi.id, name=wi.name, unit=wi.unit)
                if kind == "equipment":
                    data["name"] = f"{wi.name} (cho: {bname})"[:500]
                    stats["install_lines"] += 1
                    install_wis.add(wi.id)
                if details:
                    data["details"] = [
                        {"text": str(d.get("text") or "")[:500], "expr": _qty_expr(str(d.get("expr") or "0"), factor)}
                        for d in details
                    ]
                else:
                    data["quantity_expr"] = _qty_expr(_fmt(qty_d) or "0", factor)
                if factor != 1:
                    stats["converted"] += 1
                stats["matched"] += 1
                memories.append((memory_key(bname), parse_unit(bunit).base[:30], wi.id))
            else:
                custom_seq += 1
                data.update(
                    custom_code=f"TT.{custom_seq:02d}",
                    name=bname[:500] or "(Công tác tạm tính)",
                    unit=bunit[:30] or "đv",
                )
                if details:
                    data["details"] = [
                        {"text": str(d.get("text") or "")[:500], "expr": str(d.get("expr") or "0")} for d in details
                    ]
                else:
                    data["quantity"] = str(qty_d)
                stats["custom"] += 1
            lines_payload.append(data)

    if errors:
        transaction.set_rollback(True)
        raise ValidationError({"detail": "Chưa nhập được: " + " · ".join(errors[:10])})

    ser = EstimateLineSerializer(data=lines_payload, many=True)
    if not ser.is_valid():
        transaction.set_rollback(True)
        msgs = [f"dòng {k + 1}: {v}" for k, v in enumerate(ser.errors) if v]
        raise ValidationError({"detail": "Dữ liệu dòng không hợp lệ — " + "; ".join(msgs[:10])})
    if lines_payload:
        ser.save()
    stats["equipment_in_norm"] = _zero_equipment_materials(revision, install_wis, user)
    # Hạng mục chỉ có thiết bị không kèm công lắp đặt → không giữ hạng mục rỗng
    empty, _ = ProjectItem.objects.filter(revision=revision, lines__isnull=True, order__gt=order0).delete()
    created_items -= empty

    for key, base, wi_id in memories:
        obj, created = BoqMatchMemory.objects.get_or_create(
            release_id=release_id, key=key, unit_base=base, defaults={"work_item_id": wi_id}
        )
        if not created:
            BoqMatchMemory.objects.filter(pk=obj.pk).update(work_item_id=wi_id, hits=F("hits") + 1)

    result = {
        "items_created": created_items,
        "lines_created": len(lines_payload),
        "default_items_removed": removed,
        **stats,
    }
    record(user, "boq.import", revision, {**result, "file": str(payload.get("filename") or "")[:200]})
    return result
