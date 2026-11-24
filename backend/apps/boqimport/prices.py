"""Tự áp giá còn thiếu trong dự toán từ các bảng giá vật tư (công bố giá của Sở; giá tham khảo từ dự toán F1).

Ba loại chỗ trống được điền (không bao giờ ghi đè giá người dùng đã nhập):
1. Vật liệu trong hao phí định mức chưa có giá → giá riêng của dự toán (ResourceOverride, ghi nguồn).
2. Dòng tạm tính (không mã định mức) chưa có đơn giá → đơn giá VL tạm tính (manual_vl), vd "Cáp Cat6".
3. Thiết bị chưa có đơn giá → đơn giá thiết bị, vd "Ổ cắm HDMI", "Thanh nguồn PDU".

Thứ tự nguồn: công bố giá chính thức mới nhất của địa phương → các bảng giá tham khảo từ dự toán (F1).

Bộ giá dự toán (PriceObservation) hiện chỉ có nhân công và ca máy; giá vật liệu nằm trong danh mục công bố giá
(PriceCatalogItem) và trước đây phải áp tay. Ở đây chỉ áp khi KHỚP RÕ RÀNG:
- tên vật liệu trong định mức trùng tên trong công bố (bỏ phần nhóm "Lắp đặt | …", không phân biệt hoa thường);
- đơn vị cùng loại (kg ↔ tấn được quy đổi giá);
- nếu có nhiều dòng trùng tên: ưu tiên nhóm theo chương định mức (A → Xây dựng, B → Lắp đặt, S → Sửa chữa,
  C → Khảo sát, D → Thí nghiệm); còn nhiều giá khác nhau thì KHÔNG tự áp, báo để người dùng chọn.
Giá được ghi thành "giá riêng của dự toán" (ResourceOverride) kèm nguồn: không sửa dữ liệu gốc, xem / sửa được ở
sheet Tổng hợp vật tư.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from apps.audit.services import record
from apps.catalog.models import DatasetRelease, NormComponent, Resource
from apps.datasync.models import PriceCatalogItem
from apps.pricebook.models import PriceObservation
from apps.projects.models import EquipmentCost, EstimateLine, EstimateRevision, ResourceOverride

from .matcher import lower_vn, tokens
from .units import parse_unit

CHAPTER_CATEGORY = {"A": "xây dựng", "B": "lắp đặt", "S": "sửa chữa", "C": "khảo sát", "D": "thí nghiệm"}
AUTO_TAG = "Tự áp từ công bố giá"
AUTO_TAG_EST = "Tự áp từ giá tham khảo"


def _canon(s: str) -> str:
    """Chuẩn hóa tên để so: chữ thường có dấu, "mầu" → "màu", "M 5" → "M5", bỏ đuôi "các loại"."""
    s = lower_vn(s).replace("mầu", "màu")
    s = re.sub(r"\b([a-zđ])\s+(\d)", r"\1\2", s)
    s = re.sub(r"\s+các loại\s*$", "", s.strip())
    return re.sub(r"\s+", " ", s).strip(" .,;:")


_norm = _canon


def _split(name: str) -> tuple[str, str]:
    """ "Lắp đặt | Thiếc hàn" → ("lắp đặt", "thiếc hàn")."""
    if " | " in name:
        cat, base = name.split(" | ", 1)
        return _canon(cat), _canon(base)
    return "", _canon(name)


def _is_estimate(rel: DatasetRelease) -> bool:
    return (rel.meta or {}).get("source_kind") == "estimate"


def catalog_releases_for(project) -> list[DatasetRelease]:
    """Công bố giá chính thức mới nhất (có dữ liệu) của địa phương, rồi các bảng giá tham khảo từ dự toán."""
    qs = DatasetRelease.objects.filter(kind=DatasetRelease.Kind.CATALOG, status=DatasetRelease.Status.PUBLISHED)
    rels = [
        r
        for r in qs.order_by("-id")
        if (not r.region or (project.region or "").startswith(r.region))
        and PriceCatalogItem.objects.filter(release=r).exists()
    ]
    official = [r for r in rels if not _is_estimate(r)][:1]
    return official + [r for r in rels if _is_estimate(r)]


def catalog_release_for(project) -> DatasetRelease | None:
    rels = catalog_releases_for(project)
    return rels[0] if rels else None


def _label(rel: DatasetRelease) -> str:
    period = (rel.meta or {}).get("period", "")
    return f"{rel.name} {period}".strip()


def _reason(rel: DatasetRelease, item: PriceCatalogItem, note: str = "") -> str:
    price_txt = f"{item.price:,.0f}".replace(",", ".")
    spec = f" ({item.spec})" if item.spec else ""
    where = f" — tr.{item.page}" if item.page else (f" — {item.context}" if item.context else "")
    tag = AUTO_TAG_EST if _is_estimate(rel) else AUTO_TAG
    return f"{tag} {_label(rel)}: {item.name}{spec} — {price_txt} đ/{item.unit}{where}{note}"[:500]


def _convert(price: Decimal, to_unit: str, from_unit: str) -> Decimal | None:
    """Giá theo from_unit → giá theo to_unit (cùng loại đơn vị), vd 4.000.000 đ/km → 4.000 đ/m."""
    a, b = parse_unit(to_unit), parse_unit(from_unit)
    if not a.base or a.base != b.base:
        return None
    return (price * a.factor / b.factor).quantize(Decimal("1"), ROUND_HALF_UP)


def _missing_materials(revision: EstimateRevision) -> dict[str, tuple[Resource, set[str]]]:
    """{mã vật liệu: (Resource, {chữ cái chương định mức dùng nó})} chưa có giá trong bộ giá và chưa có giá riêng."""
    project = revision.project
    wi_ids = set(revision.lines_qs().exclude(work_item=None).values_list("work_item_id", flat=True))
    used: dict[str, tuple[Resource, set[str]]] = {}
    for c in NormComponent.objects.filter(
        work_item_id__in=wi_ids, kind=Resource.Kind.MATERIAL, resource__isnull=False, is_other_pct=False
    ).select_related("resource", "work_item"):
        res, chapters = used.setdefault(c.resource.code, (c.resource, set()))
        chapters.add(c.work_item.code[:1].upper())
    priced = set(
        PriceObservation.objects.filter(
            release=project.price_release,
            region=project.region,
            period=project.price_period,
            resource__code__in=used,
        ).values_list("resource__code", flat=True)
    )
    overridden = set(revision.overrides.values_list("resource__code", flat=True))
    return {k: v for k, v in used.items() if k not in priced and k not in overridden}


class _Catalog:
    """Các dòng của một bảng giá, đánh chỉ mục theo tên chuẩn hóa và theo tập âm tiết."""

    def __init__(self, rel: DatasetRelease):
        self.rel = rel
        self.rows: list[tuple[str, str, frozenset, PriceCatalogItem]] = []
        self.by_name: dict[str, list[tuple[str, PriceCatalogItem]]] = defaultdict(list)
        for item in PriceCatalogItem.objects.filter(release=rel).only(
            "name", "spec", "unit", "price", "page", "context", "document"
        ):
            cat, base = _split(item.name)
            self.by_name[base].append((cat, item))
            self.rows.append((cat, base, frozenset(tokens(base)), item))

    def material(self, res: Resource, chapters: set[str]) -> tuple[str, list[tuple[str, Decimal, PriceCatalogItem]]]:
        """→ ("exact" | "prefix" | "", [(nhóm, giá theo đơn vị vật liệu, dòng)])."""
        name = _canon(res.name)

        def conv(cands):
            out = []
            for cat, item in cands:
                price = _convert(item.price, res.unit, item.unit)
                if price is not None and price > 0:
                    out.append((cat, price, item))
            return out

        exact = conv(self.by_name.get(name, []))
        if exact:
            preferred = {CHAPTER_CATEGORY[c] for c in chapters if c in CHAPTER_CATEGORY}
            return "exact", [o for o in exact if o[0] in preferred] or exact
        prefix = conv([(cat, item) for cat, base, _, item in self.rows if base.startswith(name + " ")])
        return ("prefix", prefix) if prefix else ("", [])

    def named(self, name: str, unit: str) -> tuple[str, list[tuple[Decimal, PriceCatalogItem]]]:
        """Khớp tên một dòng BoQ (tạm tính / thiết bị) với tên trong bảng giá: mọi âm tiết số của bảng giá phải có
        trong tên BoQ, ≥ 85% âm tiết của bảng giá có trong tên BoQ, âm tiết đầu (danh từ chính) phải khớp."""
        q = set(tokens(_canon(name)))
        best: list[tuple[float, int, Decimal, PriceCatalogItem]] = []
        for _, base, toks, item in self.rows:
            if len(toks) < 2:
                continue
            words = tokens(base)
            if not words or words[0] not in q or not {t for t in toks if t[0].isdigit()} <= q:
                continue
            ratio = len(toks & q) / len(toks)
            if ratio < 0.85:
                continue
            price = _convert(item.price, unit, item.unit)
            if price is None or price <= 0:
                continue
            best.append((ratio, len(toks), price, item))
        if not best:
            return "", []
        top = max((r, n) for r, n, _, _ in best)
        return "match", [(p, it) for r, n, p, it in best if (r, n) == top]


def auto_apply_catalog_prices(revision: EstimateRevision, user) -> dict:
    out = {"catalog": None, "catalogs": [], "applied": [], "ambiguous": [], "not_found": [], "lines_filled": [],
           "equipment_filled": []}  # fmt: skip
    if revision.is_locked:
        return out
    rels = catalog_releases_for(revision.project)
    out["catalogs"] = [_label(r) for r in rels]
    out["catalog"] = " · ".join(out["catalogs"]) or None
    catalogs = [_Catalog(r) for r in rels]
    actor = user if getattr(user, "is_authenticated", False) else None

    # 1. Vật liệu trong hao phí định mức
    for code, (res, chapters) in sorted(_missing_materials(revision).items()):
        done = False
        for cat in catalogs:
            how, options = cat.material(res, chapters)
            if not options:
                continue
            prices = {p for _, p, _ in options}
            if len(prices) != 1:
                if how == "exact":  # trùng tên nhưng nhiều giá → để người dùng chọn, không lấy nguồn sau
                    out["ambiguous"].append(
                        {"code": code, "name": res.name, "unit": res.unit, "options": sorted(str(p) for p in prices)}
                    )
                    done = True
                    break
                continue
            _, price, item = options[0]
            note = " (khớp theo tên gần đúng, mọi quy cách cùng giá)" if how == "prefix" else ""
            reason = _reason(cat.rel, item, note)
            ResourceOverride.objects.create(
                revision=revision, resource=res, price=price, reason=reason, created_by=actor
            )
            out["applied"].append(
                {"code": code, "name": res.name, "unit": res.unit, "price": str(price), "source": reason}
            )
            done = True
            break
        if not done:
            out["not_found"].append({"code": code, "name": res.name, "unit": res.unit})

    def lookup(name: str, unit: str):
        for cat in catalogs:
            _, winners = cat.named(name, unit)
            if not winners:
                continue
            if len({p for p, _ in winners}) == 1:
                return cat, winners[0][1], winners[0][0]
            return None  # nhiều giá → không đoán
        return None

    # 2. Dòng tạm tính chưa có đơn giá
    for ln in revision.lines_qs().filter(work_item__isnull=True, manual_vl__isnull=True, manual_nc__isnull=True,
                                         manual_m__isnull=True):  # fmt: skip
        found = lookup(ln.name, ln.unit)
        if not found:
            continue
        cat, item, price = found
        reason = _reason(cat.rel, item)
        EstimateLine.objects.filter(pk=ln.pk).update(manual_vl=price, note=f"{ln.note} · Giá VL: {reason}"[:500])
        out["lines_filled"].append({"name": ln.name, "unit": ln.unit, "price": str(price), "source": reason})

    # 3. Thiết bị chưa có đơn giá
    for eq in revision.equipment.filter(unit_price=0):
        name = re.sub(r"\s*\[[^\]]*\]\s*$", "", eq.name)  # bỏ "[tên hạng mục]" do bước nhập BoQ thêm vào
        found = lookup(name, eq.unit)
        if not found:
            continue
        cat, item, price = found
        reason = _reason(cat.rel, item)
        EquipmentCost.objects.filter(pk=eq.pk).update(unit_price=price, note=f"{eq.note} · {reason}"[:500])
        out["equipment_filled"].append({"name": name, "unit": eq.unit, "price": str(price), "source": reason})

    if out["applied"] or out["lines_filled"] or out["equipment_filled"]:
        record(
            user,
            "prices.auto_apply",
            revision,
            {
                "applied": [a["code"] for a in out["applied"]],
                "lines_filled": len(out["lines_filled"]),
                "equipment_filled": len(out["equipment_filled"]),
            },
        )
    return out
