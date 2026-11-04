"""Engine core: per-line pricing (Phụ lục IV TT 36/2026, công thức 4.1–4.4) and
Bảng 3.8 summary (Phụ lục III TT 36/2026)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .hashing import sha256_of
from .quantity import QuantityError, evaluate
from .rounding import RoundingPolicy
from .snapshot import LineInput, Snapshot

ENGINE_VERSION = "0.2.0"
ZERO = Decimal("0")
ONE = Decimal("1")
BN = Decimal("1000000000")  # 1 tỷ đồng


@dataclass
class Warning_:
    code: str
    message: str
    line_id: str | None = None
    resource_code: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class LineResult:
    line_id: str
    item_id: str
    code: str
    name: str
    unit: str
    quantity: Decimal
    unit_vl: Decimal
    unit_nc: Decimal
    unit_m: Decimal
    vl: Decimal
    nc: Decimal
    m: Decimal
    direct: Decimal
    breakdown: dict[str, Any]
    warnings: list[Warning_] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        d = {
            "line_id": self.line_id,
            "item_id": self.item_id,
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "quantity": str(self.quantity),
            "unit_vl": str(self.unit_vl),
            "unit_nc": str(self.unit_nc),
            "unit_m": str(self.unit_m),
            "vl": str(self.vl),
            "nc": str(self.nc),
            "m": str(self.m),
            "direct": str(self.direct),
            "breakdown": self.breakdown,
            "warnings": [w.to_json() for w in self.warnings],
        }
        return d


@dataclass
class EngineResult:
    engine_version: str
    input_hash: str
    output_hash: str
    lines: list[LineResult]
    resource_totals: list[dict[str, Any]]
    summary: dict[str, Any]
    warnings: list[Warning_]

    def to_json(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "lines": [ln.to_json() for ln in self.lines],
            "resource_totals": self.resource_totals,
            "summary": self.summary,
            "warnings": [w.to_json() for w in self.warnings],
        }


# --------------------------------------------------------------------------- per-line pricing


def _resolve_quantity(line: LineInput, rp: RoundingPolicy, warnings: list[Warning_]) -> Decimal:
    if line.quantity_expr.strip():
        try:
            q = evaluate(line.quantity_expr, line.variables)
        except QuantityError as e:
            warnings.append(Warning_("QUANTITY_EXPR", str(e), line.id))
            q = line.quantity if line.quantity is not None else ZERO
    else:
        q = line.quantity if line.quantity is not None else ZERO
    if q < 0:
        warnings.append(Warning_("NEGATIVE_QUANTITY", "Khối lượng âm", line.id))
    return rp.qty(q)


def price_line(line: LineInput, snap: Snapshot, rp: RoundingPolicy) -> LineResult:
    warnings: list[Warning_] = []
    q = _resolve_quantity(line, rp, warnings)

    if line.work_item_unit and line.unit and line.work_item_unit.strip().lower() != line.unit.strip().lower():
        warnings.append(
            Warning_(
                "UNIT_MISMATCH", f"Đơn vị dòng '{line.unit}' khác đơn vị định mức '{line.work_item_unit}'", line.id
            )
        )
    manual = {"vl": line.manual_vl, "nc": line.manual_nc, "m": line.manual_m}
    has_manual = any(v is not None for v in manual.values())
    if not line.work_item_found:
        if has_manual:
            warnings.append(Warning_("CUSTOM_ITEM", f"Mã tạm tính {line.code}: dùng đơn giá nhập tay", line.id))
        else:
            warnings.append(
                Warning_("WORK_ITEM_NOT_FOUND", f"Mã công tác không có trong bộ định mức: {line.code}", line.id)
            )
    if not line.components and not has_manual:
        warnings.append(Warning_("NO_NORM", "Không có thành phần hao phí và chưa nhập đơn giá tạm tính", line.id))
    if has_manual:
        warnings.append(
            Warning_(
                "MANUAL_UNIT_PRICE",
                "Đơn giá tạm tính nhập tay: "
                + ", ".join(f"{k.upper()} {v}" for k, v in manual.items() if v is not None),
                line.id,
            )
        )

    sums = {"MATERIAL": ZERO, "LABOR": ZERO, "MACHINE": ZERO}
    other_pct = {"MATERIAL": ZERO, "MACHINE": ZERO}
    comps: list[dict[str, Any]] = []

    for c in line.components:
        if c.is_other_pct:
            other_pct[c.kind] = other_pct.get(c.kind, ZERO) + c.quantity
            comps.append({"kind": c.kind, "other_pct": str(c.quantity)})
            continue
        if c.quantity < 0:
            warnings.append(Warning_("NEGATIVE_NORM", "Hao phí định mức âm", line.id, c.resource_code))
        res = snap.resources.get(c.resource_code or "")
        price_in = snap.prices.get(c.resource_code or "")
        entry: dict[str, Any] = {
            "resource_code": c.resource_code,
            "kind": c.kind,
            "name": res.name if res else None,
            "unit": res.unit if res else None,
            "norm_qty": str(c.quantity),
            "consumption": str(rp.consumption(q * c.quantity)),
        }
        if res is None:
            warnings.append(
                Warning_("RESOURCE_NOT_FOUND", f"Nguồn lực không tồn tại: {c.resource_code}", line.id, c.resource_code)
            )
        if price_in is None:
            warnings.append(
                Warning_(
                    "MISSING_PRICE",
                    f"Thiếu giá cho {c.resource_code} tại kỳ/địa phương của dự án",
                    line.id,
                    c.resource_code,
                )
            )
            entry.update({"price": None, "price_source": None, "amount_per_unit": None})
        else:
            if price_in.status != "approved":
                warnings.append(
                    Warning_(
                        "PRICE_NOT_APPROVED",
                        f"Giá {c.resource_code} chưa được duyệt ({price_in.source})",
                        line.id,
                        c.resource_code,
                    )
                )
            per_unit = c.quantity * price_in.price  # chi phí cho 1 đơn vị công tác, chưa làm tròn
            sums[c.kind] = sums.get(c.kind, ZERO) + per_unit
            entry.update(
                {"price": str(price_in.price), "price_source": price_in.source, "amount_per_unit": str(per_unit)}
            )
        comps.append(entry)

    # 4.1: VL = Σ(Vi × Gi) × (1 + Kvl); 4.3: NC = Σ(Ni × Gi); 4.4: M = Σ(Mj × Gj) × (1 + Kmtc)
    k_vl = other_pct["MATERIAL"] / Decimal(100)
    k_m_other = other_pct["MACHINE"] / Decimal(100)
    unit_vl_raw = sums["MATERIAL"] * (ONE + k_vl)
    unit_nc_raw = sums["LABOR"]
    unit_m_raw = sums["MACHINE"] * (ONE + k_m_other)
    if manual["vl"] is not None:
        unit_vl_raw = manual["vl"]
    if manual["nc"] is not None:
        unit_nc_raw = manual["nc"]
    if manual["m"] is not None:
        unit_m_raw = manual["m"]
    unit_vl, unit_nc, unit_m = rp.price(unit_vl_raw), rp.price(unit_nc_raw), rp.price(unit_m_raw)

    # Bảng 3.8: VL = ΣQ×Dvl ; NC = ΣQ×Dnc×Knc ; M = ΣQ×Dm×Km
    vl = rp.money(q * unit_vl)
    nc = rp.money(q * unit_nc * line.k_nc)
    m = rp.money(q * unit_m * line.k_m)
    direct = vl + nc + m

    breakdown = {
        "quantity": {
            "expr": line.quantity_expr,
            "details": line.quantity_details,
            "value": str(q),
            "rounding": rp.quantity,
        },
        "components": comps,
        "k_other": {"material_pct": str(other_pct["MATERIAL"]), "machine_pct": str(other_pct["MACHINE"])},
        "unit_prices": {
            "vl_raw": str(unit_vl_raw),
            "nc_raw": str(unit_nc_raw),
            "m_raw": str(unit_m_raw),
            "rounding": rp.unit_price,
            "manual": {k: (None if v is None else str(v)) for k, v in manual.items()},
        },
        "factors": {"k_nc": str(line.k_nc), "k_m": str(line.k_m)},
        "amount_rounding": rp.amount,
        "formulas": {
            "unit_vl": "Σ(V_i × G_i) × (1 + K_vl)  [4.1]",
            "unit_nc": "Σ(N_i × G_i)  [4.3]",
            "unit_m": "Σ(M_j × G_j) × (1 + K_mtc)  [4.4]",
            "vl": "Q × D_vl",
            "nc": "Q × D_nc × K_nc",
            "m": "Q × D_m × K_m",
        },
    }
    return LineResult(
        line_id=line.id,
        item_id=line.item_id,
        code=line.code,
        name=line.name,
        unit=line.unit,
        quantity=q,
        unit_vl=unit_vl,
        unit_nc=unit_nc,
        unit_m=unit_m,
        vl=vl,
        nc=nc,
        m=m,
        direct=direct,
        breakdown=breakdown,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- resource totals (Tổng hợp vật tư)


def resource_totals(
    lines: list[LineInput], results: list[LineResult], snap: Snapshot, rp: RoundingPolicy
) -> list[dict[str, Any]]:
    totals: dict[str, Decimal] = {}
    qty_by_line = {r.line_id: r.quantity for r in results}
    for line in lines:
        q = qty_by_line[line.id]
        for c in line.components:
            if c.is_other_pct or not c.resource_code:
                continue
            totals[c.resource_code] = totals.get(c.resource_code, ZERO) + rp.consumption(q * c.quantity)
    out = []
    for code in sorted(totals):
        res = snap.resources.get(code)
        price = snap.prices.get(code)
        amount = rp.money(totals[code] * price.price) if price else None
        out.append(
            {
                "resource_code": code,
                "kind": res.kind if res else None,
                "name": res.name if res else code,
                "unit": res.unit if res else None,
                "quantity": str(totals[code]),
                "price": str(price.price) if price else None,
                "price_source": price.source if price else None,
                "amount": str(amount) if amount is not None else None,
            }
        )
    return out


# --------------------------------------------------------------------------- Bảng 3.8 summary


def _pick_column(thresholds: list[str], basis_bn: Decimal) -> int:
    for i, t in enumerate(thresholds):
        if basis_bn <= Decimal(t):
            return i
    return len(thresholds)


def _pct(v: str | Decimal) -> Decimal:
    return Decimal(str(v)) / Decimal(100)


def summarize(snap: Snapshot, results: list[LineResult], rp: RoundingPolicy) -> tuple[dict[str, Any], list[Warning_]]:
    rules = snap.rule_pack
    p = snap.params
    warnings: list[Warning_] = []
    ct = p.construction_type

    VL = sum((r.vl for r in results), ZERO)
    NC = sum((r.nc for r in results), ZERO)
    M = sum((r.m for r in results), ZERO)
    T = VL + NC + M

    vat_rate = p.vat_rate if p.vat_rate is not None else Decimal(str(rules["vat_rate"]))
    remote = Decimal(str(rules.get("remote_area_coeff", "1.1"))) if p.is_remote_area else ONE

    # ---- chi phí chung C
    overhead_detail: dict[str, Any]
    if p.overhead_basis == "LABOR":
        tbl = rules["overhead_labor"]
        row = tbl["rows"].get(p.labor_overhead_row)
        if row is None:
            raise ValueError(f"Rule pack không có dòng Bảng 3.4 cho '{p.labor_overhead_row}'")
        col = _pick_column(tbl["thresholds_bn"], NC / BN)
        rate = Decimal(row[col]) * remote
        C = rp.money(NC * _pct(rate))
        overhead_detail = {
            "basis": "LABOR",
            "table": "3.4",
            "row": p.labor_overhead_row,
            "column": col,
            "basis_value_bn": str(NC / BN),
            "rate_pct": str(rate),
            "remote_coeff": str(remote),
        }
        basis_bn_for_tables = None
    else:
        tbl = rules["overhead_direct"]
        row = tbl["rows"].get(ct)
        if row is None:
            raise ValueError(f"Rule pack không có dòng Bảng 3.3 cho loại công trình '{ct}'")
        basis_bn_for_tables = p.approved_construction_cost_bn
        if p.is_feasibility_report_only:
            col = int(tbl.get("feasibility_report_only_column", 0))
            basis_note = "Báo cáo KT-KT → cột ≤40"
        elif basis_bn_for_tables is not None:
            col = _pick_column(tbl["thresholds_bn"], basis_bn_for_tables)
            basis_note = "Theo chi phí XD trước thuế trong TMĐT được duyệt"
        else:
            # Chưa có TMĐT duyệt: lặp điểm bất động trên GXDTT tính ra (bậc thang → hội tụ nhanh)
            col = _pick_column(tbl["thresholds_bn"], T / BN)
            for _ in range(6):
                g = _gxdtt(T, NC, rules, ct, Decimal(row[col]) * remote, rp)
                new_col = _pick_column(tbl["thresholds_bn"], g / BN)
                if new_col == col:
                    break
                col = new_col
            basis_bn_for_tables = _gxdtt(T, NC, rules, ct, Decimal(row[col]) * remote, rp) / BN
            basis_note = "Chưa có TMĐT duyệt: ngưỡng chọn theo chi phí XD trước thuế tính ra (cần xác nhận)"
            warnings.append(Warning_("THRESHOLD_BASIS_DERIVED", basis_note))
        rate = Decimal(row[col]) * remote
        C = rp.money(T * _pct(rate))
        overhead_detail = {
            "basis": "DIRECT",
            "table": "3.3",
            "row": ct,
            "column": col,
            "basis_value_bn": str(basis_bn_for_tables) if basis_bn_for_tables is not None else None,
            "basis_note": basis_note,
            "rate_pct": str(rate),
            "remote_coeff": str(remote),
        }

    # ---- chi phí một số công việc không xác định được KL (Bảng 3.5)
    tt_rate = Decimal(str(rules["unquantified_work"]["rows"][ct]))
    TT = rp.money(T * _pct(tt_rate))
    GT = C + TT

    # ---- thu nhập chịu thuế tính trước (Bảng 3.6)
    tl_rate = Decimal(str(rules["taxable_income"]["rows"][ct]))
    TL = rp.money((T + GT) * _pct(tl_rate))
    GXDTT = T + GT + TL
    GTGT = rp.money(GXDTT * vat_rate)
    GXD = GXDTT + GTGT

    # ---- nhà tạm (Bảng 3.7)
    th = rules["temp_housing"]
    th_row = th["rows"]["LINEAR" if p.is_linear else "OTHER"]
    th_basis = basis_bn_for_tables if basis_bn_for_tables is not None else GXDTT / BN
    th_col = _pick_column(th["thresholds_bn"], th_basis)
    lt_rate = Decimal(th_row[th_col])
    LT = rp.money(GXDTT * _pct(lt_rate))
    LT_GTGT = rp.money(LT * vat_rate)
    LT_SAU_THUE = LT + LT_GTGT

    rows = [
        {"stt": "I", "key": "T", "label": "Chi phí trực tiếp", "formula": "VL + NC + M", "value": str(T)},
        {"stt": "1", "key": "VL", "label": "Chi phí vật liệu", "formula": "ΣQj × Djvl", "value": str(VL)},
        {"stt": "2", "key": "NC", "label": "Chi phí nhân công", "formula": "ΣQj × Djnc × Knc", "value": str(NC)},
        {
            "stt": "3",
            "key": "M",
            "label": "Chi phí máy và thiết bị thi công",
            "formula": "ΣQj × Djm × Km",
            "value": str(M),
        },
        {"stt": "II", "key": "GT", "label": "Chi phí gián tiếp", "formula": "C + TT", "value": str(GT)},
        {
            "stt": "1",
            "key": "C",
            "label": "Chi phí chung",
            "formula": f"{'NC' if p.overhead_basis == 'LABOR' else 'T'} × {overhead_detail['rate_pct']}%",
            "value": str(C),
            "rate_pct": overhead_detail["rate_pct"],
        },
        {
            "stt": "2",
            "key": "TT",
            "label": "Chi phí một số công việc không xác định được khối lượng từ thiết kế",
            "formula": f"T × {tt_rate}%",
            "value": str(TT),
            "rate_pct": str(tt_rate),
        },
        {
            "stt": "III",
            "key": "TL",
            "label": "Thu nhập chịu thuế tính trước",
            "formula": f"(T + GT) × {tl_rate}%",
            "value": str(TL),
            "rate_pct": str(tl_rate),
        },
        {
            "stt": "",
            "key": "GXDTT",
            "label": "Chi phí xây dựng trước thuế",
            "formula": "T + GT + TL",
            "value": str(GXDTT),
        },
        {
            "stt": "IV",
            "key": "GTGT",
            "label": "Thuế giá trị gia tăng",
            "formula": f"GXDTT × {vat_rate * 100}%",
            "value": str(GTGT),
            "rate_pct": str(vat_rate * 100),
        },
        {"stt": "", "key": "GXD", "label": "Chi phí xây dựng sau thuế", "formula": "GXDTT + GTGT", "value": str(GXD)},
        {
            "stt": "V",
            "key": "LT",
            "label": "Chi phí nhà tạm để ở và điều hành thi công (trước thuế)",
            "formula": f"GXDTT × {lt_rate}%",
            "value": str(LT),
            "rate_pct": str(lt_rate),
        },
        {
            "stt": "",
            "key": "LT_GTGT",
            "label": "Thuế GTGT nhà tạm",
            "formula": f"LT × {vat_rate * 100}%",
            "value": str(LT_GTGT),
        },
        {
            "stt": "",
            "key": "LT_SAU_THUE",
            "label": "Chi phí nhà tạm sau thuế",
            "formula": "LT + LT_GTGT",
            "value": str(LT_SAU_THUE),
        },
        {
            "stt": "",
            "key": "TONG",
            "label": "Tổng chi phí xây dựng sau thuế kể cả nhà tạm",
            "formula": "GXD + LT_SAU_THUE",
            "value": str(GXD + LT_SAU_THUE),
        },
    ]
    items = _item_summaries(
        snap,
        results,
        rp,
        overhead_rate=Decimal(overhead_detail["rate_pct"]),
        overhead_on_labor=p.overhead_basis == "LABOR",
        tt_rate=tt_rate,
        tl_rate=tl_rate,
        vat_rate=vat_rate,
    )
    summary = {
        "table": "Bảng 3.8 Phụ lục III TT 36/2026/TT-BXD",
        "items": items,
        "construction_type": ct,
        "rows": rows,
        "values": {r["key"]: r["value"] for r in rows},
        "overhead": overhead_detail,
        "temp_housing": {
            "table": "3.7",
            "row": "LINEAR" if p.is_linear else "OTHER",
            "column": th_col,
            "basis_value_bn": str(th_basis),
            "rate_pct": str(lt_rate),
        },
        "vat_rate": str(vat_rate),
        "rule_pack": {"code": rules.get("code"), "version": rules.get("version")},
        "rounding": rp.__dict__,
    }
    return summary, warnings


def _item_summaries(
    snap: Snapshot,
    results: list[LineResult],
    rp: RoundingPolicy,
    *,
    overhead_rate: Decimal,
    overhead_on_labor: bool,
    tt_rate: Decimal,
    tl_rate: Decimal,
    vat_rate: Decimal,
) -> list[dict[str, Any]]:
    """Tổng hợp kinh phí theo từng hạng mục (THKP hạng mục / TH chi phí XD).

    Tỷ lệ (chọn theo quy mô cả công trình) áp lại cho từng hạng mục; do làm tròn từng bước,
    tổng các hạng mục có thể lệch vài đồng so với dòng toàn công trình.
    """
    names: dict[str, str] = {}
    order: list[str] = []
    for ln in snap.lines:
        if ln.item_id not in names:
            names[ln.item_id] = ln.item_name
            order.append(ln.item_id)
    acc: dict[str, dict[str, Decimal]] = {i: {"VL": ZERO, "NC": ZERO, "M": ZERO, "n": ZERO} for i in order}
    for r in results:
        a = acc[r.item_id]
        a["VL"] += r.vl
        a["NC"] += r.nc
        a["M"] += r.m
        a["n"] += ONE
    out = []
    for item_id in order:
        a = acc[item_id]
        T = a["VL"] + a["NC"] + a["M"]
        C = rp.money((a["NC"] if overhead_on_labor else T) * _pct(overhead_rate))
        TT = rp.money(T * _pct(tt_rate))
        GT = C + TT
        TL = rp.money((T + GT) * _pct(tl_rate))
        GXDTT = T + GT + TL
        GTGT = rp.money(GXDTT * vat_rate)
        vals = {
            "VL": a["VL"],
            "NC": a["NC"],
            "M": a["M"],
            "T": T,
            "C": C,
            "TT": TT,
            "GT": GT,
            "TL": TL,
            "GXDTT": GXDTT,
            "GTGT": GTGT,
            "GXD": GXDTT + GTGT,
        }
        out.append(
            {
                "item_id": item_id,
                "name": names[item_id],
                "lines": int(a["n"]),
                "values": {k: str(v) for k, v in vals.items()},
            }
        )
    return out


def _gxdtt(T: Decimal, NC: Decimal, rules: dict, ct: str, overhead_rate: Decimal, rp: RoundingPolicy) -> Decimal:
    C = rp.money(T * _pct(overhead_rate))
    TT = rp.money(T * _pct(rules["unquantified_work"]["rows"][ct]))
    GT = C + TT
    TL = rp.money((T + GT) * _pct(rules["taxable_income"]["rows"][ct]))
    return T + GT + TL


# --------------------------------------------------------------------------- entry point


def run(snap: Snapshot) -> EngineResult:
    rp = RoundingPolicy.from_dict(snap.rounding or snap.rule_pack.get("rounding"))
    input_hash = sha256_of({"engine_version": ENGINE_VERSION, "snapshot": snap.to_json()})
    lines_sorted = sorted(snap.lines, key=lambda ln: (ln.item_id, ln.order, ln.id))
    results = [price_line(ln, snap, rp) for ln in lines_sorted]
    totals = resource_totals(lines_sorted, results, snap, rp)
    summary, swarn = summarize(snap, results, rp)
    warnings = [w for r in results for w in r.warnings] + swarn
    if not snap.rule_pack.get("review", {}).get("approved", False):
        warnings.append(Warning_("RULE_PACK_NOT_APPROVED", "Rule pack chưa được kỹ sư dự toán ký duyệt"))
    body = {
        "lines": [r.to_json() for r in results],
        "resource_totals": totals,
        "summary": summary,
    }
    output_hash = sha256_of({"engine_version": ENGINE_VERSION, "input_hash": input_hash, **body})
    return EngineResult(ENGINE_VERSION, input_hash, output_hash, results, totals, summary, warnings)
