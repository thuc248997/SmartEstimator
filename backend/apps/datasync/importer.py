"""Nạp dữ liệu đã bóc tách vào CSDL: mỗi lần cập nhật tạo bản phát hành (DatasetRelease) mới, không sửa bản cũ."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.catalog.models import DatasetRelease, NormComponent, Resource, SourceDocument, WorkItem
from apps.pricebook.models import PriceObservation

from .models import PriceCatalogItem
from .parsers import hanoi_prices, tt38
from .parsers.match import MachineMatcher, canonical_labor
from .sources import Candidate

HN_REGIONS = ["Hà Nội - Vùng I", "Hà Nội - Vùng II"]
KIND_PREFIX = {"MATERIAL": "VL", "LABOR": "NC", "MACHINE": "M"}


def _version(kind: str, name: str, version: str) -> str:
    """unique_together (kind, name, version): nạp lại cùng tài liệu (force) → thêm hậu tố (2), (3)…"""
    version = version[:44]
    n = DatasetRelease.objects.filter(kind=kind, name=name, version__startswith=version).count()
    return version if n == 0 else f"{version} ({n + 1})"


def _date(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def source_document(c: Candidate) -> SourceDocument:
    issuer = c.issuer or "Không rõ"
    number = c.number or c.title[:90] or c.urls[0][-90:]
    doc = SourceDocument.objects.filter(issuer=issuer, sha256=c.sha256).first()
    if doc:
        return doc
    if SourceDocument.objects.filter(issuer=issuer, number=number).exists():
        number = f"{number} #{c.sha256[:8]}"  # cùng số hiệu nhưng tệp khác (bản sửa) → giữ cả hai để truy vết
    return SourceDocument.objects.create(
        issuer=issuer,
        number=number[:100],
        title=(c.title or number)[:500],
        url=c.urls[0][:200],
        sha256=c.sha256,
        issued_on=_date(c.issued_on),
        effective_from=_date(c.effective_from) or _date(c.issued_on),
    )


def find_installed(c: Candidate, kind: str) -> DatasetRelease | None:
    return (
        DatasetRelease.objects.filter(kind=kind, source__sha256=c.sha256, status=DatasetRelease.Status.PUBLISHED)
        .order_by("-id")
        .first()
    )


def _resource_code(kind: str, name: str, unit: str) -> str:
    key = f"{kind}|{name.strip().lower()}|{unit.strip().lower()}"
    return f"TT38.{KIND_PREFIX[kind]}.{hashlib.sha1(key.encode()).hexdigest()[:10]}"


LABOR_CODES = {
    "Nhân công nhóm 1": "NC.N1",
    "Nhân công nhóm 2": "NC.N2",
    "Nhân công nhóm 3": "NC.N3",
    "Nhân công nhóm 4": "NC.N4",
    "Nhân công vận hành, điều khiển máy": "NC.VHM",
    "Lái xe": "NC.LAIXE",
    "Nhân công vận hành tàu thuyền": "NC.TAU",
    "Kỹ sư": "NC.KYSU",
    "Thợ lặn": "NC.THOLAN",
    "Nghệ nhân": "NC.NGHENHAN",
}


# --------------------------------------------------------------------------- định mức TT 38


@transaction.atomic
def import_norms(c: Candidate, records: list[tt38.NormRecord], report: tt38.ParseReport) -> DatasetRelease:
    doc = source_document(c)
    by_appendix = Counter(r.appendix for r in records)
    rel = DatasetRelease.objects.create(
        kind=DatasetRelease.Kind.NORM,
        name=f"Định mức xây dựng {c.number or 'TT 38/2026/TT-BXD'}",
        version=_version(
            "NORM",
            f"Định mức xây dựng {c.number or 'TT 38/2026/TT-BXD'}",
            f"{(c.issued_on or '')[:10]} #{c.sha256[:8]}",
        ),
        region="VN",
        effective_from=_date(c.effective_from) or _date(c.issued_on),
        status=DatasetRelease.Status.PUBLISHED,
        source=doc,
        is_sample=False,
        notes=(
            "Bóc tách tự động từ PDF chính thức theo tọa độ chữ. Mỗi mã ghi số trang nguồn để đối chiếu; "
            f"{len(report.skipped_tables)} bảng chưa bóc được (xem meta.report)."
        ),
        meta={
            "documents": [{"number": c.number, "url": c.urls[0], "sha256": c.sha256, "note": c.note}],
            "report": {
                "pages": report.pages,
                "tables": report.tables,
                "work_items": len(records),
                "by_appendix": dict(sorted(by_appendix.items())),
                "skipped_tables": report.skipped_tables[:500],
                "duplicate_codes": len(report.warnings),
            },
        },
    )
    # nguồn lực: nhân công theo nhóm (mã cố định), vật liệu / máy theo tên + đơn vị
    wanted: dict[str, tuple[str, str, str]] = {}
    for r in records:
        for comp in r.components:
            if comp.is_other_pct:
                continue
            if comp.kind == "LABOR":
                canon = canonical_labor(comp.name) or comp.name
                code = LABOR_CODES.get(canon, _resource_code("LABOR", canon, comp.unit))
                wanted.setdefault(code, ("LABOR", canon, comp.unit or "công"))
            else:
                wanted.setdefault(_resource_code(comp.kind, comp.name, comp.unit), (comp.kind, comp.name, comp.unit))
    existing = set(Resource.objects.filter(code__in=wanted).values_list("code", flat=True))
    Resource.objects.bulk_create(
        [
            Resource(code=code, kind=k, name=n[:300], unit=(u or "")[:30])
            for code, (k, n, u) in wanted.items()
            if code not in existing
        ],
        batch_size=2000,
    )
    res_id = dict(Resource.objects.filter(code__in=wanted).values_list("code", "id"))

    items = WorkItem.objects.bulk_create(
        [
            WorkItem(
                release=rel,
                code=r.code[:30],
                name=r.name[:500],
                unit=(r.unit or "")[:30],
                group_code=(r.group_code or r.code[:5])[:30],
                notes=f"Phụ lục {r.appendix} — trang {r.page} PDF; nhóm: {r.group_name}"[:1000],
            )
            for r in records
        ],
        batch_size=2000,
    )
    comps = []
    for wi, r in zip(items, records, strict=False):
        for comp in r.components:
            q = Decimal(comp.quantity)
            if q < 0:
                continue
            if comp.is_other_pct:
                comps.append(NormComponent(work_item=wi, resource=None, kind=comp.kind, quantity=q, is_other_pct=True))
                continue
            if comp.kind == "LABOR":
                canon = canonical_labor(comp.name) or comp.name
                code = LABOR_CODES.get(canon, _resource_code("LABOR", canon, comp.unit))
            else:
                code = _resource_code(comp.kind, comp.name, comp.unit)
            comps.append(NormComponent(work_item=wi, resource_id=res_id[code], kind=comp.kind, quantity=q))
    NormComponent.objects.bulk_create(comps, batch_size=5000)
    rel.meta["report"]["components"] = len(comps)
    rel.meta["report"]["resources"] = len(wanted)
    rel.save(update_fields=["meta"])
    return rel


# --------------------------------------------------------------------------- giá nhân công + ca máy Hà Nội


def _latest_published(kind: str, sid: str) -> DatasetRelease | None:
    return DatasetRelease.objects.filter(kind=kind, meta__source_id=sid, status="published").order_by("-id").first()


@transaction.atomic
def import_hn_prices(labor: Candidate | None, machine: Candidate | None) -> DatasetRelease:
    """Một bộ giá Hà Nội = đơn giá nhân công + giá ca máy (2 vùng). Vật liệu: danh mục tham khảo riêng."""
    labor_rows = hanoi_prices.parse_labor(labor.text) if labor else []
    machine_rows = hanoi_prices.parse_machines(machine.text) if machine else []
    docs = [x for x in (labor, machine) if x]
    period = max((d.issued_on for d in docs), default="")[:7]
    rel = DatasetRelease.objects.create(
        kind=DatasetRelease.Kind.PRICE,
        name="Giá nhân công, ca máy Hà Nội",
        version=_version("PRICE", "Giá nhân công, ca máy Hà Nội", " + ".join(d.number for d in docs) or period),
        region="Hà Nội",
        effective_from=_date(max((d.issued_on for d in docs), default="")),
        status=DatasetRelease.Status.PUBLISHED,
        source=source_document(docs[0]),
        is_sample=False,
        notes="Giá chưa VAT. Vùng I/II theo danh mục phường, xã trong quyết định. Máy trong định mức được ghép "
        "theo tên với bảng giá ca máy (xem meta.report.unmatched_machines).",
        meta={
            "source_id": "hn-prices",
            "regions": HN_REGIONS,
            "period": period,
            "documents": [
                {
                    "kind": k,
                    "number": d.number,
                    "issued_on": d.issued_on,
                    "url": d.urls[0],
                    "sha256": d.sha256,
                    "note": d.note,
                }
                for k, d in (("labor", labor), ("machine", machine))
                if d
            ],
        },
    )
    for d in docs:
        source_document(d)
    obs: list[PriceObservation] = []

    def add(resource: Resource, prices: tuple[str, str], note: str):
        for region, p in zip(HN_REGIONS, prices, strict=False):
            obs.append(
                PriceObservation(
                    release=rel,
                    resource=resource,
                    region=region,
                    period=period,
                    price=Decimal(p),
                    unit=resource.unit,
                    source_kind="OFFICIAL",
                    status="approved",
                    note=note[:500],
                )
            )

    for lp in labor_rows:
        code = LABOR_CODES[lp.name]
        res, _ = Resource.objects.get_or_create(code=code, defaults={"kind": "LABOR", "name": lp.name, "unit": "công"})
        add(res, (lp.vung1, lp.vung2), f"{labor.number} ngày {labor.issued_on}")

    unmatched: Counter = Counter()
    matched = 0
    if machine_rows:
        matcher = MachineMatcher([(m.code, m.name) for m in machine_rows])
        by_code = {m.code: m for m in machine_rows}
        usage = Counter(
            NormComponent.objects.filter(resource__kind="MACHINE", resource__code__startswith="TT38.").values_list(
                "resource_id", flat=True
            )
        )
        for res in Resource.objects.filter(kind="MACHINE", code__startswith="TT38."):
            hit = matcher.match(res.name)
            if hit is None:
                unmatched[res.name] += usage.get(res.id, 0)
                continue
            m = by_code[hit[0]]
            add(res, (m.vung1, m.vung2), f"{machine.number}: {m.code} {m.name}")
            matched += 1
    PriceObservation.objects.bulk_create(obs, batch_size=5000)
    rel.meta["report"] = {
        "labor_rows": len(labor_rows),
        "machine_rows": len(machine_rows),
        "machines_matched": matched,
        "unmatched_machines": [n for n, _ in unmatched.most_common(300)],
        "observations": len(obs),
    }
    rel.save(update_fields=["meta"])
    return rel


# --------------------------------------------------------------------------- danh mục giá vật liệu


@transaction.atomic
def import_hn_materials(c: Candidate) -> DatasetRelease:
    rows = []
    for f, text in zip(c.files, c.texts, strict=False):
        for m in hanoi_prices.parse_materials(text):
            rows.append((f, m))
    rel = DatasetRelease.objects.create(
        kind=DatasetRelease.Kind.CATALOG,
        name="Công bố giá vật liệu xây dựng Hà Nội",
        version=_version("CATALOG", "Công bố giá vật liệu xây dựng Hà Nội", c.period or c.issued_on or c.sha256[:8]),
        region="Hà Nội",
        effective_from=_date(c.issued_on),
        status=DatasetRelease.Status.PUBLISHED,
        source=source_document(c),
        notes="Danh mục tham khảo, giá chưa VAT, chưa gồm vận chuyển đến hiện trường (trừ khi ghi khác). "
        "Dùng 'Áp giá thông báo' để gán cho vật liệu của dự toán.",
        meta={
            "source_id": "hn-material",
            "period": c.period,
            "title": c.title,
            "documents": [{"url": u, "sha256": f.sha256} for u, f in zip(c.urls, c.files, strict=False)],
        },
    )
    PriceCatalogItem.objects.bulk_create(
        [
            PriceCatalogItem(
                release=rel,
                name=m.name[:500],
                spec=m.spec[:500],
                unit=m.unit[:30],
                price=Decimal(m.price),
                context=m.context[:500],
                page=m.page,
                document=re.sub(r"^.*/", "", f.url)[:200],
            )
            for f, m in rows
        ],
        batch_size=5000,
    )
    rel.meta["report"] = {"items": len(rows)}
    rel.save(update_fields=["meta"])
    return rel
