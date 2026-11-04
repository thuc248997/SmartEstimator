"""Kiểm tra & cập nhật dữ liệu: chọn văn bản mới nhất của từng nguồn, so mã băm với bản đã nạp,
chỉ tải / bóc tách / nạp khi có bản mới."""

from __future__ import annotations

import traceback

from django.utils import timezone

from apps.catalog.models import DatasetRelease

from . import importer
from .models import DataUpdateRun
from .parsers import hanoi_prices, tt38
from .sources import (
    Candidate,
    fill_doc_info,
    hn_portal_candidate,
    load_manifest,
    manifest_candidates,
    pdf_bbox,
    pdf_text,
)

ALL_SOURCES = ["tt38-2026", "hn-prices", "hn-material"]
# Ngưỡng an toàn: bảng đọc được quá ít dòng → coi là tệp sai định dạng, không nạp
MIN_LABOR_ROWS = 4
MIN_MACHINE_ROWS = 50
MIN_NORM_RECORDS = 1000
TITLES = {
    "tt38-2026": "Định mức xây dựng (Thông tư 38/2026/TT-BXD, 8 phụ lục)",
    "hn-prices": "Đơn giá nhân công + giá ca máy Hà Nội",
    "hn-material": "Công bố giá vật liệu xây dựng Hà Nội",
}


def _doc(c: Candidate) -> dict:
    return {
        "number": c.number,
        "issued_on": c.issued_on,
        "title": c.title,
        "url": c.urls[0],
        "origin": c.origin,
        "note": c.note,
        "sha256": c.sha256,
    }


def _newest(cands: list[Candidate], log) -> list[Candidate]:
    ok = []
    for c in cands:
        try:
            fill_doc_info(c)
            ok.append(c)
        except Exception as e:  # noqa: BLE001 — một nguồn lỗi không làm hỏng cả lượt
            log(f"  ! Không tải được {c.urls[0]}: {type(e).__name__}: {e}")
    return sorted(ok, key=lambda c: c.issued_on or "", reverse=True)


def _known_newer(manifest: dict, sid: str, chosen: Candidate) -> list[str]:
    out = []
    for k in manifest.get("sources", {}).get(sid, {}).get("known_newer", []):
        if (k.get("issued_on") or "") > (chosen.issued_on or ""):
            out.append(
                f"Có văn bản mới hơn {k['number']} ngày {k['issued_on']} nhưng chưa có tệp tải về: {k.get('note', '')}"
            )
    return out


def update_norms(manifest: dict, log, force: bool = False) -> dict:
    cands = _newest(manifest_candidates(manifest, "tt38-2026"), log)
    if not cands:
        return {"status": "error", "message": "Không tải được văn bản định mức từ nguồn nào"}
    c = cands[0]
    installed = importer.find_installed(c, DatasetRelease.Kind.NORM)
    if installed and not force:
        return {
            "status": "up_to_date",
            "message": f"Đã là bản mới nhất: {c.number} (bản phát hành #{installed.id})",
            "release_id": installed.id,
            "document": _doc(c),
        }
    log(f"  Bóc tách {c.number} ({c.files[0].size // 1024} KB)…")
    records, report = tt38.parse_tt38(pdf_bbox(c.files[0].path))
    if len(records) < MIN_NORM_RECORDS:
        return {
            "status": "error",
            "message": f"Bóc tách chỉ được {len(records)} mã — nghi tệp sai định dạng, không nạp",
        }
    rel = importer.import_norms(c, records, report)
    return {
        "status": "updated",
        "message": f"Đã nạp {len(records)} mã định mức từ {c.number}",
        "release_id": rel.id,
        "document": _doc(c),
        "report": rel.meta.get("report", {}),
    }


def _pick_parsable(cands: list[Candidate], parse, log) -> tuple[Candidate | None, list[str]]:
    warns = []
    for c in cands:
        try:
            c.text = pdf_text(c.files[0].path)
            parse(c.text)
            return c, warns
        except Exception as e:  # noqa: BLE001
            warns.append(f"{c.number or c.urls[0]}: không đọc được bảng ({e}); dùng văn bản trước đó")
            log("  ! " + warns[-1])
    return None, warns


def update_hn_prices(manifest: dict, log, force: bool = False) -> dict:
    labor_c = [x for x in [_safe(hn_portal_candidate, "hn-labor", log)] if x] + manifest_candidates(
        manifest, "hn-labor"
    )
    mach_c = [x for x in [_safe(hn_portal_candidate, "hn-machine", log)] if x] + manifest_candidates(
        manifest, "hn-machine"
    )
    labor, w1 = _pick_parsable(_newest(labor_c, log), _at_least(hanoi_prices.parse_labor, lambda: MIN_LABOR_ROWS), log)
    machine, w2 = _pick_parsable(
        _newest(mach_c, log), _at_least(hanoi_prices.parse_machines, lambda: MIN_MACHINE_ROWS), log
    )
    warnings = w1 + w2
    if machine:
        warnings += _known_newer(manifest, "hn-machine", machine)
    if labor:
        warnings += _known_newer(manifest, "hn-labor", labor)
    if not labor and not machine:
        return {"status": "error", "message": "Không lấy được bảng giá nhân công / ca máy Hà Nội", "warnings": warnings}
    shas = sorted(d.sha256 for d in (labor, machine) if d)
    docs = [_doc(d) for d in (labor, machine) if d]
    for rel in DatasetRelease.objects.filter(kind="PRICE", meta__source_id="hn-prices", status="published").order_by(
        "-id"
    )[:5]:
        if sorted(x.get("sha256", "") for x in rel.meta.get("documents", [])) == shas and not force:
            return {
                "status": "up_to_date",
                "message": "Đã là bản mới nhất: " + " + ".join(d["number"] for d in docs),
                "release_id": rel.id,
                "documents": docs,
                "warnings": warnings,
            }
    rel = importer.import_hn_prices(labor, machine)
    rep = rel.meta.get("report", {})
    return {
        "status": "updated",
        "message": f"Đã nạp giá Hà Nội: {rep.get('labor_rows', 0)} nhóm nhân công, {rep.get('machine_rows', 0)} máy "
        f"(ghép được {rep.get('machines_matched', 0)} máy của định mức)",
        "release_id": rel.id,
        "documents": docs,
        "warnings": warnings,
        "report": rep,
    }


def update_hn_material(manifest: dict, log, force: bool = False) -> dict:
    cands = [x for x in [_safe(hn_portal_candidate, "hn-material", log)] if x] + manifest_candidates(
        manifest, "hn-material"
    )
    cands = _newest(cands, log)
    if not cands:
        return {"status": "error", "message": "Không tìm thấy công bố giá vật liệu trên cổng Sở Xây dựng Hà Nội"}
    c = cands[0]
    if c.period and (not c.number or not c.number[0].isdigit()):
        y, q = c.period.split("-Q")
        c.number = f"Công bố giá VLXD quý {['I', 'II', 'III', 'IV'][int(q) - 1]}/{y}"
    installed = importer.find_installed(c, DatasetRelease.Kind.CATALOG)
    if installed and not force:
        return {
            "status": "up_to_date",
            "message": f"Đã là bản mới nhất: {c.title}",
            "release_id": installed.id,
            "document": _doc(c),
        }
    c.texts = [pdf_text(f.path) for f in c.files]
    rel = importer.import_hn_materials(c)
    return {
        "status": "updated",
        "message": f"Đã nạp {rel.meta['report']['items']} dòng giá vật liệu ({c.title})",
        "release_id": rel.id,
        "document": _doc(c),
    }


def _at_least(parse, n):
    def check(text: str):
        n_min = n() if callable(n) else n
        rows = parse(text)
        if len(rows) < n_min:
            raise ValueError(f"chỉ đọc được {len(rows)} dòng")
        return rows

    return check


def _safe(fn, arg, log):
    try:
        return fn(arg)
    except Exception as e:  # noqa: BLE001 — cổng Sở lỗi thì vẫn dùng nguồn trong manifest
        log(f"  ! Không dò được cổng Sở Xây dựng ({arg}): {type(e).__name__}: {e}")
        return None


RUNNERS = {"tt38-2026": update_norms, "hn-prices": update_hn_prices, "hn-material": update_hn_material}


def run_update(run_id: int, force: bool = False) -> DataUpdateRun:
    run = DataUpdateRun.objects.get(pk=run_id)
    run.status = DataUpdateRun.Status.RUNNING
    run.save(update_fields=["status"])
    lines: list[str] = []

    def log(msg: str):
        lines.append(msg)
        DataUpdateRun.objects.filter(pk=run.pk).update(log="\n".join(lines))

    try:
        manifest = load_manifest()
        if manifest.get("remote_manifest_error"):
            log("! Không đọc được danh sách nguồn từ xa: " + manifest["remote_manifest_error"])
        results = []
        norms_updated = False
        for sid in run.sources or ALL_SOURCES:
            log(f"Kiểm tra: {TITLES.get(sid, sid)}")
            try:
                # định mức mới → ghép lại giá máy theo nguồn lực mới
                r = RUNNERS[sid](manifest, log, force=force or (sid == "hn-prices" and norms_updated))
            except Exception as e:  # noqa: BLE001
                r = {"status": "error", "message": f"{type(e).__name__}: {e}"}
                log(traceback.format_exc(limit=3))
            if sid == "tt38-2026" and r["status"] == "updated":
                norms_updated = True
            r = {"source": sid, "title": TITLES.get(sid, sid), **r}
            results.append(r)
            log(f"  → {r['status']}: {r['message']}")
            DataUpdateRun.objects.filter(pk=run.pk).update(results=results)
        run.refresh_from_db()
        run.results = results
        run.status = DataUpdateRun.Status.DONE
    except Exception as e:  # noqa: BLE001
        run.status = DataUpdateRun.Status.FAILED
        run.error = f"{type(e).__name__}: {e}"
    run.finished_at = timezone.now()
    run.log = "\n".join(lines)
    run.save()
    return run
