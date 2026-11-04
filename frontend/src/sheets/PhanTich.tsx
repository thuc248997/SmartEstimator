import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ColGroupDef } from "ag-grid-community";
import { fmt, Revision, Run } from "../api";
import { COL_LETTERS, xlTheme } from "../gridTheme";

type Row = { rid: string; head: boolean; stt?: number; code: string; name: string; unit: string; norm?: string; qty?: string; cons?: string; price?: string | null; amount?: number | null; source?: string | null; kind?: string };

const KIND: Record<string, string> = { MATERIAL: "VL", LABOR: "NC", MACHINE: "M" };

export default function PhanTich({ revision, run }: { revision: Revision; run: Run | null }) {
  const rows = useMemo(() => {
    const out: Row[] = [];
    if (!run?.lines) return out;
    const byLine = new Map(run.lines.map((l) => [l.line, l]));
    let stt = 0;
    for (const item of [...revision.items].sort((a, b) => a.order - b.order || a.id - b.id)) {
      for (const line of [...item.lines].sort((a, b) => a.order - b.order || a.id - b.id)) {
        const c = byLine.get(line.id);
        if (!c) continue;
        stt += 1;
        out.push({ rid: `h${line.id}`, head: true, stt, code: c.code, name: c.name, unit: c.unit, qty: c.quantity });
        c.breakdown.components.forEach((comp, i) => {
          if (comp.other_pct !== undefined) {
            out.push({ rid: `c${line.id}-${i}`, head: false, code: "", name: `${comp.kind === "MATERIAL" ? "Vật liệu" : "Máy"} khác`, unit: "%", norm: comp.other_pct, kind: comp.kind });
            return;
          }
          const cons = Number(comp.consumption ?? 0);
          out.push({ rid: `c${line.id}-${i}`, head: false, code: comp.resource_code ?? "", name: comp.name ?? comp.resource_code ?? "", unit: comp.unit ?? "",
            norm: comp.norm_qty, qty: c.quantity, cons: comp.consumption, price: comp.price ?? null,
            amount: comp.price == null ? null : Math.round(cons * Number(comp.price)), source: comp.price_source, kind: comp.kind });
        });
      }
    }
    return out;
  }, [revision, run]);

  const cols: ColDef<Row>[] = [
    { headerName: "STT", field: "stt", width: 56, cellClass: "num" },
    { headerName: "Mã hiệu", field: "code", width: 120, cellStyle: (p) => (p.data?.head ? { fontWeight: "700" } : { paddingLeft: "18px" }) as Record<string, string> },
    { headerName: "Loại", width: 56, valueGetter: (p) => (p.data?.kind ? KIND[p.data.kind] : ""), cellStyle: { color: "#616161" } },
    { headerName: "Tên công tác / hao phí", field: "name", flex: 1, minWidth: 280, tooltipField: "name" },
    { headerName: "Đơn vị", field: "unit", width: 70 },
    { headerName: "Định mức", field: "norm", width: 100, cellClass: "num", valueFormatter: (p) => fmt.qty(p.value, 4) },
    { headerName: "Khối lượng", field: "qty", width: 100, cellClass: "num", valueFormatter: (p) => fmt.qty(p.value) },
    { headerName: "Hao phí", field: "cons", width: 120, cellClass: "num", valueFormatter: (p) => fmt.qty(p.value, 4) },
    { headerName: "Đơn giá", field: "price", width: 110, cellClass: (p) => `num ${p.data && !p.data.head && p.data.unit !== "%" && p.data.price == null ? "err-cell" : ""} ${p.data?.source?.startsWith("override:") ? "override" : ""}`,
      valueFormatter: (p) => (p.data && !p.data.head && p.data.unit !== "%" && p.value == null ? "THIẾU GIÁ" : fmt.money(p.value)) },
    { headerName: "Thành tiền", field: "amount", width: 124, cellClass: "num", valueFormatter: (p) => fmt.money(p.value) },
    { headerName: "Nguồn giá", field: "source", width: 240, tooltipField: "source", cellStyle: { color: "#616161" } },
  ];
  const columnDefs: (ColDef<Row> | ColGroupDef<Row>)[] = [
    { headerName: "", children: [{ headerName: "", width: 46, pinned: "left", cellClass: "rownum", valueGetter: (p) => (p.node?.rowIndex ?? 0) + 1 }] },
    ...cols.map((c, i) => ({ headerName: COL_LETTERS[i], children: [c] })),
  ];

  if (!run?.lines) return <div className="sheet-pad">Chưa có kết quả tính. Bấm <strong>Tính lại (F9)</strong>.</div>;
  return (
    <div className="sheet">
      <AgGridReact<Row> theme={xlTheme} rowData={rows} columnDefs={columnDefs} getRowId={(p) => p.data.rid} groupHeaderHeight={20}
        defaultColDef={{ resizable: true, sortable: false, suppressMovable: true, suppressHeaderMenuButton: true }}
        getRowClass={(p) => (p.data?.head ? "item-row" : "")} tooltipShowDelay={300} />
    </div>
  );
}
