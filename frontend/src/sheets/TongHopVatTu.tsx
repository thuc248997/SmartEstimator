import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ColGroupDef, ICellRendererParams } from "ag-grid-community";
import { fmt, ResourceTotal, Run } from "../api";
import TextEditor from "../TextEditor";
import { COL_LETTERS, xlTheme } from "../gridTheme";

type Row = { rid: string; head?: string; stt?: number; t?: ResourceTotal; amount?: number | null; note?: string };
/** Mã nội bộ của nguồn lực bóc từ TT 38 (TT38.VL.<hash>) không có nghĩa với người dùng → ẩn. */
export const displayCode = (c?: string | null) => (c && c.startsWith("TT38.") ? "" : c ?? "");
const KINDS: [string, string][] = [["MATERIAL", "I. VẬT LIỆU"], ["LABOR", "II. NHÂN CÔNG"], ["MACHINE", "III. MÁY THI CÔNG"]];

export default function TongHopVatTu({ run, locked, onOverride }: { run: Run | null; locked: boolean; onOverride(t: ResourceTotal, price: string): void }) {
  const { rows, total } = useMemo(() => {
    const out: Row[] = [];
    let sum = 0;
    const totals = run?.result?.resource_totals ?? [];
    const values = run?.result?.summary.values ?? {};
    const lineTotal: Record<string, number> = { MATERIAL: Number(values.VL ?? 0), LABOR: Number(values.NC ?? 0), MACHINE: Number(values.M ?? 0) };
    for (const [kind, label] of KINDS) {
      const list = totals.filter((t) => t.kind === kind);
      if (!list.length && !lineTotal[kind]) continue;
      const sub = list.reduce((s, t) => s + Number(t.amount ?? 0), 0);
      // Reconcile with Tiên lượng: "VL/Máy khác %" (K_vl, K_mtc in 4.1/4.4), Knc/Km and per-step rounding
      const diff = lineTotal[kind] - sub;
      out.push({ rid: `h${kind}`, head: label, amount: sub + diff });
      list.forEach((t, i) => out.push({ rid: t.resource_code, stt: i + 1, t, amount: t.amount == null ? null : Number(t.amount) }));
      if (Math.abs(diff) >= 1) {
        const why = kind === "MATERIAL" ? "Vật liệu khác (% định mức) và làm tròn" : kind === "MACHINE" ? "Máy khác (% định mức), hệ số Km và làm tròn" : "Hệ số Knc và làm tròn";
        out.push({ rid: `d${kind}`, note: why, amount: diff });
      }
      sum += sub + diff;
    }
    return { rows: out, total: { rid: "total", head: "TỔNG CỘNG", amount: sum } as Row };
  }, [run]);

  const cols: ColDef<Row>[] = [
    { headerName: "STT", width: 56, cellClass: "num", valueGetter: (p) => p.data?.stt ?? null },
    { headerName: "Mã", width: 130, valueGetter: (p) => p.data?.head ?? displayCode(p.data?.t?.resource_code), colSpan: (p) => (p.data?.head ? 4 : 1) },
    { headerName: "Tên vật tư / nhân công / máy", flex: 1, minWidth: 260, valueGetter: (p) => p.data?.t?.name ?? p.data?.note,
      cellStyle: (p) => (p.data?.note ? { fontStyle: "italic", color: "#616161" } : null) },
    { headerName: "Đơn vị", width: 72, valueGetter: (p) => p.data?.t?.unit },
    { headerName: "Khối lượng", width: 130, cellClass: "num", valueGetter: (p) => p.data?.t?.quantity ?? null, valueFormatter: (p) => fmt.qty(p.value, 4) },
    { colId: "price", headerName: "Đơn giá", width: 120, editable: (p) => !locked && !!p.data?.t, cellEditor: TextEditor,
      valueGetter: (p) => p.data?.t?.price ?? null,
      valueSetter: (p) => { if (p.data?.t) onOverride(p.data.t, String(p.newValue ?? "")); return false; },
      cellClass: (p) => `num ${!locked && p.data?.t ? "editable-cell" : ""} ${p.data?.t?.price_source?.startsWith("override:") ? "override" : ""} ${p.data?.t && p.data.t.price == null ? "err-cell" : ""}`,
      valueFormatter: (p) => (p.data?.t && p.value == null ? "THIẾU GIÁ" : fmt.money(p.value)),
      tooltipValueGetter: (p) => (p.data?.t ? (locked ? "Bản đã khóa" : "Sửa trực tiếp để nhập giá riêng cho dự án (có lý do, được lưu vết)") : undefined) },
    { headerName: "Thành tiền", width: 140, cellClass: "num", valueGetter: (p) => p.data?.amount ?? null, valueFormatter: (p) => fmt.money(p.value), cellStyle: { fontWeight: 600 } },
    { headerName: "Nguồn giá", width: 300, valueGetter: (p) => p.data?.t?.price_source ?? "",
      cellRenderer: (p: ICellRendererParams<Row>) => {
        const s = String(p.value ?? "");
        return s.startsWith("override:") ? <span style={{ color: "#1d4ed8" }}>✎ Giá riêng: {s.slice(9)}</span> : <span style={{ color: "#616161" }}>{s}</span>;
      } },
  ];
  const columnDefs: (ColDef<Row> | ColGroupDef<Row>)[] = [
    { headerName: "", children: [{ headerName: "", width: 46, pinned: "left", cellClass: "rownum", valueGetter: (p) => (p.node?.rowPinned ? "" : (p.node?.rowIndex ?? 0) + 1) }] },
    ...cols.map((c, i) => ({ headerName: COL_LETTERS[i], children: [c] })),
  ];
  if (!run?.result) return <div className="sheet-pad">Chưa có kết quả tính. Bấm <strong>Tính lại (F9)</strong>.</div>;
  return (
    <div className="sheet">
      <AgGridReact<Row> theme={xlTheme} rowData={rows} pinnedBottomRowData={[total]} columnDefs={columnDefs} getRowId={(p) => p.data.rid}
        groupHeaderHeight={20} defaultColDef={{ resizable: true, sortable: false, suppressMovable: true, suppressHeaderMenuButton: true }}
        getRowClass={(p) => (p.data?.head ? (p.node.rowPinned ? "total-row" : "item-row") : "")} stopEditingWhenCellsLoseFocus tooltipShowDelay={300} />
    </div>
  );
}
