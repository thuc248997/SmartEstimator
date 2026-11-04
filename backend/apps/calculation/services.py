"""Bridge between the ORM and the pure engine: build a Snapshot, run, persist."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import NormComponent, Resource
from apps.pricebook.models import PriceObservation
from apps.projects.models import EstimateRevision

from .engine import ENGINE_VERSION, LineInput, NormLine, PriceInput, ProjectParams, ResourceRef, Snapshot, run
from .models import CalculationLine, CalculationRun

BLOCKING_WARNINGS = {
    "MISSING_PRICE",
    "WORK_ITEM_NOT_FOUND",
    "RESOURCE_NOT_FOUND",
    "QUANTITY_EXPR",
    "NEGATIVE_QUANTITY",
    "NEGATIVE_NORM",
}


def build_snapshot(revision: EstimateRevision) -> Snapshot:
    project = revision.project
    lines: list[LineInput] = []
    resource_codes: set[str] = set()
    comps_by_wi: dict[int, list[NormComponent]] = {}

    est_lines = list(
        revision.lines_qs().select_related("work_item", "item").order_by("item__order", "item_id", "order", "id")
    )
    wi_ids = {ln.work_item_id for ln in est_lines if ln.work_item_id}
    for c in NormComponent.objects.filter(work_item_id__in=wi_ids).select_related("resource"):
        comps_by_wi.setdefault(c.work_item_id, []).append(c)

    for ln in est_lines:
        comps = []
        for c in comps_by_wi.get(ln.work_item_id, []):
            code = c.resource.code if c.resource_id else None
            if code:
                resource_codes.add(code)
            comps.append(NormLine(code, c.kind, c.quantity, c.is_other_pct))
        lines.append(
            LineInput(
                id=str(ln.id),
                item_id=str(ln.item_id),
                item_name=ln.item.name,
                order=ln.order,
                code=ln.code,
                name=ln.name,
                unit=ln.unit,
                quantity_expr=ln.quantity_expr or "",
                quantity=ln.quantity,
                k_nc=ln.k_nc,
                k_m=ln.k_m,
                components=comps,
                work_item_found=ln.work_item_id is not None,
                work_item_unit=ln.work_item.unit if ln.work_item_id else None,
                manual_vl=ln.manual_vl,
                manual_nc=ln.manual_nc,
                manual_m=ln.manual_m,
                quantity_details=list(ln.details or []),
            )
        )

    resources = {
        r.code: ResourceRef(r.code, r.kind, r.name, r.unit) for r in Resource.objects.filter(code__in=resource_codes)
    }
    prices: dict[str, PriceInput] = {}
    for p in PriceObservation.objects.filter(
        release=project.price_release,
        region=project.region,
        period=project.price_period,
        resource__code__in=resource_codes,
    ).select_related("resource"):
        status = "approved" if p.status == PriceObservation.Status.APPROVED else "pending"
        prices[p.resource.code] = PriceInput(
            p.price, f"release:{project.price_release.name}:{p.region}:{p.period}:{p.source_kind}", status
        )
    for ov in revision.overrides.select_related("resource"):
        prices[ov.resource.code] = PriceInput(ov.price, f"override:{ov.reason}", "approved")

    params = ProjectParams(
        construction_type=project.construction_type,
        overhead_basis=project.overhead_basis,
        labor_overhead_row=project.labor_overhead_row,
        is_remote_area=project.is_remote_area,
        is_linear=project.is_linear,
        is_feasibility_report_only=project.is_feasibility_report_only,
        approved_construction_cost_bn=project.approved_construction_cost_bn,
        vat_rate=project.vat_rate,
    )
    return Snapshot(lines=lines, resources=resources, prices=prices, rule_pack=project.rule_pack.data, params=params)


def start_calculation(revision: EstimateRevision) -> CalculationRun:
    """Create a run; execute synchronously for small revisions, else enqueue a Celery task."""
    from .tasks import execute_run

    run_obj = CalculationRun.objects.create(revision=revision, engine_version=ENGINE_VERSION)
    n_lines = revision.lines_qs().count()
    if n_lines <= settings.CALC_SYNC_LINE_LIMIT or settings.CELERY_TASK_ALWAYS_EAGER:
        execute_run_now(run_obj.id)
    else:
        res = execute_run.delay(run_obj.id)
        CalculationRun.objects.filter(pk=run_obj.pk).update(celery_task_id=res.id)
    run_obj.refresh_from_db()
    return run_obj


def execute_run_now(run_id: int) -> CalculationRun:
    run_obj = CalculationRun.objects.select_related("revision__project").get(pk=run_id)
    run_obj.status = CalculationRun.Status.RUNNING
    run_obj.save(update_fields=["status"])
    try:
        revision = run_obj.revision
        # Revision đã khóa → tính lại từ snapshot đã lưu, không lấy giá mới
        snap = (
            Snapshot.from_json(revision.snapshot)
            if revision.is_locked and revision.snapshot
            else build_snapshot(revision)
        )
        result = run(snap)
        with transaction.atomic():
            run_obj.snapshot = snap.to_json()
            run_obj.input_hash = result.input_hash
            run_obj.output_hash = result.output_hash
            run_obj.result = {"summary": result.summary, "resource_totals": result.resource_totals}
            run_obj.warnings = [w.to_json() for w in result.warnings]
            run_obj.status = CalculationRun.Status.DONE
            run_obj.finished_at = timezone.now()
            run_obj.save()
            CalculationLine.objects.bulk_create(
                [
                    CalculationLine(
                        run=run_obj,
                        line_id=int(r.line_id),
                        quantity=r.quantity,
                        unit_vl=r.unit_vl,
                        unit_nc=r.unit_nc,
                        unit_m=r.unit_m,
                        vl=r.vl,
                        nc=r.nc,
                        m=r.m,
                        direct=r.direct,
                        breakdown=r.breakdown,
                        warnings=[w.to_json() for w in r.warnings],
                    )
                    for r in result.lines
                ]
            )
    except Exception as e:  # noqa: BLE001 — persist failure state for the API
        run_obj.status = CalculationRun.Status.FAILED
        run_obj.error = f"{type(e).__name__}: {e}"
        run_obj.finished_at = timezone.now()
        run_obj.save()
        raise
    return run_obj


def explain_line(run_obj: CalculationRun, line_id: int) -> dict:
    cl = run_obj.lines.select_related("line__work_item", "line__item").get(line_id=line_id)
    ln = cl.line
    return {
        "line": {
            "id": ln.id,
            "code": ln.code,
            "name": ln.name,
            "unit": ln.unit,
            "item": ln.item.name,
            "work_item": ln.work_item_id,
            "quantity_expr": ln.quantity_expr,
        },
        "quantity": str(cl.quantity),
        "unit_prices": {"vl": str(cl.unit_vl), "nc": str(cl.unit_nc), "m": str(cl.unit_m)},
        "amounts": {"vl": str(cl.vl), "nc": str(cl.nc), "m": str(cl.m), "direct": str(cl.direct)},
        "breakdown": cl.breakdown,
        "warnings": cl.warnings,
        "engine_version": run_obj.engine_version,
        "input_hash": run_obj.input_hash,
        "rule_pack": run_obj.snapshot.get("rule_pack", {}).get("code") if run_obj.snapshot else None,
    }


def decimal_or_none(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))
