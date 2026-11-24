"""Tự áp giá vật liệu từ công bố giá địa phương cho các vật liệu trong dự toán chưa có giá.

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
from apps.projects.models import EstimateRevision, ResourceOverride

from .matcher import lower_vn
from .units import parse_unit

CHAPTER_CATEGORY = {"A": "xây dựng", "B": "lắp đặt", "S": "sửa chữa", "C": "khảo sát", "D": "thí nghiệm"}
AUTO_TAG = "Tự áp từ công bố giá"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", lower_vn(s)).strip(" .,;")


def _split(name: str) -> tuple[str, str]:
    """ "Lắp đặt | Thiếc hàn" → ("lắp đặt", "thiếc hàn")."""
    if " | " in name:
        cat, base = name.split(" | ", 1)
        return _norm(cat), _norm(base)
    return "", _norm(name)


def catalog_release_for(project) -> DatasetRelease | None:
    qs = DatasetRelease.objects.filter(kind=DatasetRelease.Kind.CATALOG, status=DatasetRelease.Status.PUBLISHED)
    rels = [r for r in qs.order_by("-id") if not r.region or (project.region or "").startswith(r.region)]
    for r in rels:
        if PriceCatalogItem.objects.filter(release=r).exists():
            return r
    return None


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


def auto_apply_catalog_prices(revision: EstimateRevision, user) -> dict:
    out = {"catalog": None, "applied": [], "ambiguous": [], "not_found": []}
    if revision.is_locked:
        return out
    missing = _missing_materials(revision)
    if not missing:
        return out
    rel = catalog_release_for(revision.project)
    if rel is None:
        out["not_found"] = [{"code": k, "name": r.name, "unit": r.unit} for k, (r, _) in missing.items()]
        return out
    period = (rel.meta or {}).get("period", "")
    out["catalog"] = f"{rel.name} {period}".strip()

    by_name: dict[str, list[tuple[str, PriceCatalogItem]]] = defaultdict(list)
    wanted = {_norm(r.name) for r, _ in missing.values()}
    for item in PriceCatalogItem.objects.filter(release=rel).only("name", "spec", "unit", "price", "page", "document"):
        cat, base = _split(item.name)
        if base in wanted:
            by_name[base].append((cat, item))

    for code, (res, chapters) in sorted(missing.items()):
        ru = parse_unit(res.unit)
        options = []
        for cat, item in by_name.get(_norm(res.name), []):
            cu = parse_unit(item.unit)
            if not ru.base or ru.base != cu.base:
                continue
            # giá theo đơn vị của vật liệu trong định mức (vd công bố theo kg, định mức theo tấn)
            price = (item.price * ru.factor / cu.factor).quantize(Decimal("1"), ROUND_HALF_UP)
            options.append((cat, price, item))
        if not options:
            out["not_found"].append({"code": code, "name": res.name, "unit": res.unit})
            continue
        preferred = {CHAPTER_CATEGORY[c] for c in chapters if c in CHAPTER_CATEGORY}
        narrowed = [o for o in options if o[0] in preferred] or options
        prices = {p for _, p, _ in narrowed}
        if len(prices) != 1:
            out["ambiguous"].append(
                {"code": code, "name": res.name, "unit": res.unit, "options": sorted(str(p) for p in prices)}
            )
            continue
        cat, price, item = narrowed[0]
        price_txt = f"{item.price:,.0f}".replace(",", ".")
        spec = f" ({item.spec})" if item.spec else ""
        reason = f"{AUTO_TAG} {out['catalog']}: {item.name}{spec} — {price_txt} đ/{item.unit} — tr.{item.page}"[:500]
        ResourceOverride.objects.create(
            revision=revision, resource=res, price=price, reason=reason, created_by=user if user else None
        )
        out["applied"].append({"code": code, "name": res.name, "unit": res.unit, "price": str(price), "source": reason})
    if out["applied"]:
        record(user, "prices.auto_apply", revision, {"applied": [a["code"] for a in out["applied"]]})
    return out
