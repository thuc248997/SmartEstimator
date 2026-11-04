"""Load fixtures/sample_catalog.json (or a file with the same structure) into catalog + pricebook."""

import json
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from apps.pricebook.models import PriceObservation

from .models import DatasetRelease, NormComponent, Resource, WorkItem


@transaction.atomic
def load_catalog(path: Path) -> tuple[DatasetRelease, DatasetRelease]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rel = data["release"]
    norm_release, _ = DatasetRelease.objects.update_or_create(
        kind=rel["kind"],
        name=rel["name"],
        version=rel["version"],
        defaults={
            "region": rel.get("region", ""),
            "effective_from": rel.get("effective_from"),
            "is_sample": bool(rel.get("is_sample")),
            "notes": rel.get("notes", ""),
            "status": DatasetRelease.Status.PUBLISHED,
        },
    )
    prel = data["price_release"]
    price_release, _ = DatasetRelease.objects.update_or_create(
        kind=prel["kind"],
        name=prel["name"],
        version=prel["version"],
        defaults={
            "region": prel.get("region", ""),
            "effective_from": prel.get("effective_from"),
            "is_sample": bool(prel.get("is_sample")),
            "notes": prel.get("notes", ""),
            "status": DatasetRelease.Status.PUBLISHED,
        },
    )
    resources: dict[str, Resource] = {}
    for r in data["resources"]:
        grade = r.get("labor_grade")
        obj, _ = Resource.objects.update_or_create(
            code=r["code"],
            defaults={
                "kind": r["kind"],
                "name": r["name"],
                "unit": r["unit"],
                "spec": r.get("spec", ""),
                "labor_group": r.get("labor_group", "") or "",
                "labor_grade": Decimal(grade) if grade else None,
            },
        )
        resources[obj.code] = obj
    for w in data["work_items"]:
        wi, _ = WorkItem.objects.update_or_create(
            release=norm_release,
            code=w["code"],
            defaults={
                "name": w["name"],
                "unit": w["unit"],
                "group_code": w.get("group_code", ""),
                "notes": w.get("notes", ""),
            },
        )
        wi.components.all().delete()
        NormComponent.objects.bulk_create(
            [
                NormComponent(
                    work_item=wi,
                    kind=c["kind"],
                    quantity=Decimal(c["quantity"]),
                    is_other_pct=bool(c.get("is_other_pct")),
                    resource=resources[c["resource"]] if c.get("resource") else None,
                    condition=c.get("condition", ""),
                )
                for c in w["components"]
            ]
        )
    for p in data["prices"]:
        PriceObservation.objects.update_or_create(
            release=price_release,
            resource=resources[p["resource"]],
            region=p["region"],
            period=p["period"],
            defaults={
                "price": Decimal(p["price"]),
                "unit": resources[p["resource"]].unit,
                "source_kind": p["source_kind"],
                "status": p.get("status", "approved"),
                "note": p.get("note", ""),
            },
        )
    return norm_release, price_release
