from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


def _d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


@dataclass(frozen=True)
class ResourceRef:
    code: str
    kind: str  # MATERIAL | LABOR | MACHINE
    name: str
    unit: str


@dataclass(frozen=True)
class NormLine:
    resource_code: str | None
    kind: str
    quantity: Decimal  # hao phí / 1 đơn vị công tác, hoặc % nếu is_other_pct
    is_other_pct: bool = False


@dataclass(frozen=True)
class PriceInput:
    price: Decimal
    source: str  # "release:<name>:<region>:<period>" | "override:<reason>"
    status: str = "approved"  # approved | pending


@dataclass
class LineInput:
    id: str
    item_id: str
    item_name: str
    order: int
    code: str
    name: str
    unit: str
    quantity_expr: str = ""
    quantity: Decimal | None = None
    k_nc: Decimal = Decimal("1")
    k_m: Decimal = Decimal("1")
    components: list[NormLine] = field(default_factory=list)
    work_item_found: bool = True
    work_item_unit: str | None = None
    variables: dict[str, Decimal] = field(default_factory=dict)
    # Đơn giá tạm tính nhập tay (mã không có định mức, hoặc ghi đè đơn giá từng thành phần)
    manual_vl: Decimal | None = None
    manual_nc: Decimal | None = None
    manual_m: Decimal | None = None
    quantity_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectParams:
    construction_type: str
    overhead_basis: str = "DIRECT"  # DIRECT | LABOR
    labor_overhead_row: str = ""
    is_remote_area: bool = False
    is_linear: bool = False
    is_feasibility_report_only: bool = False
    approved_construction_cost_bn: Decimal | None = None
    vat_rate: Decimal | None = None


@dataclass
class Snapshot:
    lines: list[LineInput]
    resources: dict[str, ResourceRef]
    prices: dict[str, PriceInput]
    rule_pack: dict[str, Any]
    params: ProjectParams
    rounding: dict[str, Any] | None = None  # override rule_pack["rounding"]

    def to_json(self) -> dict[str, Any]:
        """Canonical form: lines sorted so input order does not affect hashes."""
        data = asdict(self)
        data["lines"] = sorted(data["lines"], key=lambda ln: (ln["item_id"], ln["order"], ln["id"]))
        data["resources"] = dict(sorted(data["resources"].items()))
        data["prices"] = dict(sorted(data["prices"].items()))
        return _jsonable(data)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Snapshot:
        lines = [
            LineInput(
                id=ln["id"],
                item_id=ln["item_id"],
                item_name=ln["item_name"],
                order=ln["order"],
                code=ln["code"],
                name=ln["name"],
                unit=ln["unit"],
                quantity_expr=ln.get("quantity_expr", ""),
                quantity=_d(ln["quantity"]) if ln.get("quantity") is not None else None,
                k_nc=_d(ln.get("k_nc", "1")),
                k_m=_d(ln.get("k_m", "1")),
                components=[
                    NormLine(c.get("resource_code"), c["kind"], _d(c["quantity"]), bool(c.get("is_other_pct")))
                    for c in ln.get("components", [])
                ],
                work_item_found=bool(ln.get("work_item_found", True)),
                work_item_unit=ln.get("work_item_unit"),
                variables={k: _d(v) for k, v in ln.get("variables", {}).items()},
                manual_vl=_opt(ln.get("manual_vl")),
                manual_nc=_opt(ln.get("manual_nc")),
                manual_m=_opt(ln.get("manual_m")),
                quantity_details=list(ln.get("quantity_details", [])),
            )
            for ln in data["lines"]
        ]
        resources = {k: ResourceRef(**v) for k, v in data["resources"].items()}
        prices = {
            k: PriceInput(_d(v["price"]), v["source"], v.get("status", "approved")) for k, v in data["prices"].items()
        }
        p = data["params"]
        params = ProjectParams(
            construction_type=p["construction_type"],
            overhead_basis=p.get("overhead_basis", "DIRECT"),
            labor_overhead_row=p.get("labor_overhead_row", ""),
            is_remote_area=bool(p.get("is_remote_area")),
            is_linear=bool(p.get("is_linear")),
            is_feasibility_report_only=bool(p.get("is_feasibility_report_only")),
            approved_construction_cost_bn=_d(p["approved_construction_cost_bn"])
            if p.get("approved_construction_cost_bn") is not None
            else None,
            vat_rate=_d(p["vat_rate"]) if p.get("vat_rate") is not None else None,
        )
        return cls(
            lines=lines,
            resources=resources,
            prices=prices,
            rule_pack=data["rule_pack"],
            params=params,
            rounding=data.get("rounding"),
        )


def _opt(v) -> Decimal | None:
    return None if v is None else _d(v)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_jsonable(v) for v in obj]
    return obj
