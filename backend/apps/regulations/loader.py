"""Load a rule pack JSON (fixtures/rule_pack_*.json) into SourceDocument + CostRulePack."""

import json
from pathlib import Path

from django.db import transaction

from apps.catalog.models import SourceDocument

from .models import CostRulePack


@transaction.atomic
def load_rule_pack(path: Path) -> CostRulePack:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    src = data.get("source") or {}
    source = None
    if src:
        source, _ = SourceDocument.objects.update_or_create(
            issuer=src["issuer"],
            number=src["number"],
            defaults={
                "title": src.get("title", ""),
                "url": src.get("url", ""),
                "issued_on": src.get("issued_on"),
                "effective_from": src.get("effective_from"),
                "errata_status": src.get("errata_status", ""),
                "needs_review_errata": bool(src.get("needs_review_errata")),
            },
        )
    pack, _ = CostRulePack.objects.update_or_create(
        code=data["code"],
        version=data["version"],
        defaults={
            "title": data.get("title", ""),
            "source": source,
            "effective_from": src.get("effective_from"),
            "data": data,
            "is_approved": bool(data.get("review", {}).get("approved", False)),
        },
    )
    return pack
