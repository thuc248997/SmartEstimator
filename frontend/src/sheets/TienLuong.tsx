import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellFocusedEvent, ColDef, ColGroupDef, GridApi, ICellRendererParams, RowClassParams, ValueGetterParams } from "ag-grid-community";
import { CalcLine, Detail, fmt, Item, Line, Revision, Run } from "../api";
import CodeEditor from "../CodeEditor";
import TextEditor from "../TextEditor";
import { COL_LETTERS, xlTheme } from "../gridTheme";

export type TLRow =
  | { rid: string; kind: "item"; itemId: number; item: Item; name: string; total: number }
  | { rid: string; kind: "line"; itemId: number; line: Line; stt: number; code: string; name: string; unit: string; quantity: string; calc?: CalcLine }
  | { rid: string; kind: "detail"; itemId: number; line: Line; idx: number; d: Detail }
  | { rid: string; kind: "dghost"; itemId: number; line: Line }
  | { rid: string; kind: "ins"; itemId: number; beforeLineId: number }
  | { rid: string; kind: "ghost"; itemId: number }
  | { rid: string; kind: "total"; itemId: 0; vl: number; nc: number; m: number; direct: number };

export type DimField = "n" | "l" | "w" | "h";
export type EditableField = "code" | "name" | "unit" | "quantity" | DimField | "manual_vl" | "manual_nc" | "manual_m";

export interface FocusInfo { ref: string; text: string; editable: boolean; field?: EditableField; row?: TLRow; hint?: string }

export interface TLHandle {
  focusedRow(): TLRow | undefined;
  /** Dòng công tác đang chọn (bôi đen nhiều dòng bằng Ctrl/Shift+click), hoặc dòng có ô đang focus. */
  selectedLines(): Line[];
  startInsert(itemId?: number, beforeLineId?: number): void;
  addDetail(lineId: number): void;
  focusLine(lineId: number): void;
}

interface Props {
  revision: Revision;
  run: Run | null;
  releaseId: number;
  locked: boolean;
  showDims: boolean;
  onEdit(row: TLRow, field: EditableField | "item_name", value: string): Promise<void> | void;
  onFocus(info: FocusInfo): void;
  onPasteRows(itemId: number, text: string): void;
  onContextMenu(row: TLRow | undefined, x: number, y: number): void;
}

/** Show stored formulas (dot decimals) the Vietnamese way: 3.5 → 3,5. */
export const viExpr = (e?: string | null) => (e ? e.replace(/(\d)\.(\d)/g, "$1,$2") : "");
/** Quantity formula: Vietnamese decimal commas → dots, "x"/"×" → "*". */
export const normExpr = (e: string) => e.replace(/^=/, "").replace(/(\d),(\d)/g, "$1.$2").replace(/[×xX](?=\s*[\d(])/g, "*").trim();
const isFormula = (s: string) => /\d/.test(s) && /^[\d\s.,()+\-*/x×X]+$/.test(s);

/** G8: "Móng M1: 1,2*1,8*0,85" → chú thích + công thức; "Ghi chú:" → dòng ghi chú; "1,2*3" → chỉ công thức. */
export function parseDetailInput(input: string): { text: string; expr: string } {
  const s = input.trim();
  if (!s) return { text: "", expr: "" };
  if (s.startsWith("=")) return { text: "", expr: normExpr(s) };
  if (s.endsWith(":")) return { text: s, expr: "" };
  const i = s.lastIndexOf(":");
  if (i > 0) {
    const right = s.slice(i + 1).trim();
    if (isFormula(right)) return { text: s.slice(0, i).trim(), expr: normExpr(right) };
  }
  if (isFormula(s)) return { text: "", expr: normExpr(s) };
  return { text: s, expr: "" };
}
export const detailLabel = (d: Detail) => (d.text && d.expr ? `${d.text}: ${viExpr(d.expr)}` : d.expr ? viExpr(d.expr) : d.text);

const num = (v?: string | number | null) => (v === undefined || v === null || v === "" ? 0 : Number(v));
const money = (p: { value: unknown }) => fmt.money(p.value as number | string | null);
const DIMS: [DimField, string][] = [["n", "Số CK"], ["l", "Dài"], ["w", "Rộng"], ["h", "Cao"]];
const MANUAL: Record<string, "manual_vl" | "manual_nc" | "manual_m"> = { unit_vl: "manual_vl", unit_nc: "manual_nc", unit_m: "manual_m" };

const TienLuong = forwardRef<TLHandle, Props>(function TienLuong({ revision, run, releaseId, locked, showDims, onEdit, onFocus, onPasteRows, onContextMenu }, ref) {
  const apiRef = useRef<GridApi<TLRow> | null>(null);
  const onEditRef = useRef(onEdit);
  onEditRef.current = onEdit;
  const pendingFocus = useRef<{ rid: string; col: string; edit?: boolean } | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [insertAt, setInsertAt] = useState<{ itemId: number; beforeLineId: number } | null>(null);

  const calcMap = useMemo(() => {
    const m = new Map<number, CalcLine>();
    run?.lines?.forEach((l) => m.set(l.line, l));
    return m;
  }, [run]);

  const { rows, total } = useMemo(() => {
    const out: TLRow[] = [];
    let stt = 0;
    const tot = { vl: 0, nc: 0, m: 0, direct: 0 };
    for (const item of [...revision.items].sort((a, b) => a.order - b.order || a.id - b.id)) {
      const lines = [...item.lines].sort((a, b) => a.order - b.order || a.id - b.id);
      const itemTotal = lines.reduce((s, l) => s + num(calcMap.get(l.id)?.direct), 0);
      out.push({ rid: `i${item.id}`, kind: "item", itemId: item.id, item, name: item.name, total: itemTotal });
      for (const line of lines) {
        if (!locked && insertAt && insertAt.beforeLineId === line.id) out.push({ rid: "ins", kind: "ins", itemId: item.id, beforeLineId: line.id });
        stt += 1;
        const calc = calcMap.get(line.id);
        if (calc) { tot.vl += num(calc.vl); tot.nc += num(calc.nc); tot.m += num(calc.m); tot.direct += num(calc.direct); }
        out.push({ rid: `l${line.id}`, kind: "line", itemId: item.id, line, stt, code: line.code, name: line.name, unit: line.unit, quantity: line.quantity, calc });
        (line.details ?? []).forEach((d, idx) => out.push({ rid: `d${line.id}-${idx}`, kind: "detail", itemId: item.id, line, idx, d }));
        if (!locked && ((line.details ?? []).length || expanded.has(line.id))) out.push({ rid: `dg${line.id}`, kind: "dghost", itemId: item.id, line });
      }
      if (!locked) out.push({ rid: `g${item.id}`, kind: "ghost", itemId: item.id });
    }
    return { rows: out, total: { rid: "total", kind: "total" as const, itemId: 0 as const, ...tot } };
  }, [revision, calcMap, locked, expanded, insertAt]);

  useEffect(() => {
    const p = pendingFocus.current;
    const api = apiRef.current;
    if (!p || !api) return;
    const node = api.getRowNode(p.rid);
    if (node && node.rowIndex !== null) {
      pendingFocus.current = null;
      api.ensureIndexVisible(node.rowIndex);
      api.setFocusedCell(node.rowIndex, p.col);
      if (p.edit) api.startEditingCell({ rowIndex: node.rowIndex, colKey: p.col });
    }
  }, [rows]);

  const isEditable = useCallback((row: TLRow | undefined, field: string): boolean => {
    if (locked || !row) return false;
    switch (row.kind) {
      case "ghost": case "ins": case "item": return field === "code";
      case "detail": case "dghost": return ["name", "quantity", "n", "l", "w", "h"].includes(field);
      case "line": {
        const custom = !row.line.work_item;
        if (field === "name" || field === "unit") return custom;
        if (field in MANUAL) return custom;
        if (field === "quantity") return !(row.line.details ?? []).length;
        return field === "code";
      }
      default: return false;
    }
  }, [locked]);

  /** Text the editor (and formula bar) starts with — may differ from the displayed value. */
  const editText = useCallback((row: TLRow, field: string): string => {
    if (row.kind === "line") {
      const l = row.line;
      if (field === "quantity") return l.quantity_expr ? `=${viExpr(l.quantity_expr)}` : fmt.qty(l.quantity, 6).replace(/\./g, "");
      if (field in MANUAL) { const v = l[MANUAL[field]]; return v == null ? "" : fmt.money(v).replace(/\./g, ""); }
      if (field === "code") return row.code;
      if (field === "name") return row.name;
      if (field === "unit") return row.unit;
    }
    if (row.kind === "detail") {
      const d = row.d;
      if (field === "name") return detailLabel(d);
      if (field === "quantity") return d.expr ? `=${viExpr(d.expr)}` : "";
      if (["n", "l", "w", "h"].includes(field)) { const v = d[field as DimField]; return v == null ? "" : viExpr(v); }
    }
    if (row.kind === "item") return row.name;
    return "";
  }, []);

  const commit = useCallback((field: EditableField) => (p: { data: TLRow; newValue: unknown }) => {
    const v = p.newValue == null ? "" : String(p.newValue).trim();
    const d = p.data;
    if (!d) return false;
    if (v === editText(d, field).trim()) return false;
    void onEditRef.current(d, field, v);
    return false;
  }, [editText]);

  const cols = useMemo<ColDef<TLRow>[]>(() => {
    const calcCol = (field: keyof CalcLine, header: string, width: number, extra: Partial<ColDef<TLRow>> = {}): ColDef<TLRow> => ({
      colId: field, headerName: header, width, cellClass: "num calc-cell", type: "rightAligned",
      valueGetter: (p: ValueGetterParams<TLRow>) => (p.data?.kind === "line" ? p.data.calc?.[field] ?? null : p.data?.kind === "total" && field in p.data ? (p.data as unknown as Record<string, number>)[field] : null),
      valueFormatter: money, ...extra,
    });
    const unitCol = (field: "unit_vl" | "unit_nc" | "unit_m", header: string, width: number): ColDef<TLRow> => calcCol(field, header, width, {
      editable: (p) => isEditable(p.data, field), cellEditor: TextEditor, valueSetter: commit(MANUAL[field]),
      cellEditorParams: { getInitial: (d: TLRow) => editText(d, field) },
      valueGetter: (p) => {
        if (p.data?.kind !== "line") return null;
        const manual = p.data.line[MANUAL[field]];
        return p.data.calc?.[field] ?? manual ?? null;
      },
      cellClass: (p) => {
        if (p.data?.kind !== "line") return "num";
        const missing = field === "unit_vl" && p.data.calc?.warnings.some((w) => w.code === "MISSING_PRICE");
        const manual = p.data.line[MANUAL[field]] != null;
        return `num ${missing ? "err-cell" : manual ? "override" : "calc-cell"} ${isEditable(p.data, field) ? "editable-cell" : ""}`;
      },
      tooltipValueGetter: (p) => (p.data?.kind === "line" && !p.data.line.work_item ? "Mã tạm tính: nhập đơn giá trực tiếp vào ô này" : undefined),
    });
    const dimCol = (field: DimField, header: string): ColDef<TLRow> => ({
      colId: field, headerName: header, width: 64, hide: !showDims, type: "rightAligned",
      editable: (p) => isEditable(p.data, field), cellEditor: TextEditor, valueSetter: commit(field),
      cellEditorParams: { getInitial: (d: TLRow) => editText(d, field) },
      valueGetter: (p) => (p.data?.kind === "detail" ? p.data.d[field] : null),
      valueFormatter: (p) => (p.value == null ? "" : fmt.qty(p.value as string, 4)),
      cellClass: (p) => `num dim-cell ${p.data && isEditable(p.data, field) ? "editable-cell" : ""}`,
    });
    return [
      { colId: "stt", headerName: "STT", width: 52, cellClass: "num",
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.stt : null) },
      { colId: "code", headerName: "Mã hiệu", width: 112,
        editable: (p) => isEditable(p.data, "code"),
        colSpan: (p) => (p.data?.kind === "item" ? 3 : p.data?.kind === "ghost" || p.data?.kind === "ins" ? 2 : p.data?.kind === "total" ? 4 : 1),
        cellEditorSelector: (p) => (p.data?.kind === "item"
          ? { component: TextEditor, params: { getInitial: (d: TLRow) => (d.kind === "item" ? d.name : "") } }
          : { component: CodeEditor, params: { releaseId }, popup: true, popupPosition: "under" }),
        valueGetter: (p) => (p.data?.kind === "item" ? p.data.name : p.data?.kind === "total" ? "TỔNG CỘNG CHI PHÍ TRỰC TIẾP" : p.data?.kind === "line" ? p.data.code : ""),
        // valueGetter differs from the stored field (ghost/item rows), so commit edits here rather than in onCellValueChanged
        valueSetter: (p) => {
          const v = p.newValue == null ? "" : String(p.newValue).trim();
          const d = p.data;
          if (!d || !v) return false;
          if (d.kind === "item") { if (v !== d.name) void onEditRef.current(d, "item_name", v); }
          else if (d.kind === "ghost" || d.kind === "ins" || (d.kind === "line" && v !== d.code)) void onEditRef.current(d, "code", v);
          return false;
        },
        cellRenderer: (p: ICellRendererParams<TLRow>) => p.data?.kind === "ghost"
          ? <span>＋ Nhập mã hiệu / từ khóa (Enter để tra mã), hoặc dán nhiều dòng từ Excel…</span>
          : p.data?.kind === "ins" ? <span>↳ Chèn công tác vào đây: gõ mã hiệu hoặc từ khóa…</span>
          : p.data?.kind === "item" ? <span>▾ {String(p.value ?? "")}</span> : String(p.value ?? ""),
        cellClass: (p) => (p.data?.kind === "line" && !p.data.line.work_item ? "warn-cell" : p.data?.kind === "line" && isEditable(p.data, "code") ? "editable-cell" : ""),
        tooltipValueGetter: (p) => (p.data?.kind === "line" && !p.data.line.work_item ? "Mã tạm tính — không có trong bộ định mức; nhập đơn giá ở các cột ĐG" : undefined) },
      { colId: "name", headerName: "Tên công tác / Diễn giải khối lượng", minWidth: 280, flex: 1,
        editable: (p) => isEditable(p.data, "name"), cellEditor: TextEditor, valueSetter: commit("name"),
        cellEditorParams: { getInitial: (d: TLRow) => editText(d, "name") },
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.name : p.data?.kind === "detail" ? detailLabel(p.data.d) : ""),
        cellRenderer: (p: ICellRendererParams<TLRow>) => {
          if (p.data?.kind === "dghost") return <span style={{ paddingLeft: 14 }}>＋ diễn giải: “Móng M1: 1,2*1,8*0,85”, “Trục A:” (ghi chú) hoặc nhập Số CK/Dài/Rộng/Cao →</span>;
          if (p.data?.kind === "detail") return <span style={{ paddingLeft: 14 }}>– {String(p.value ?? "")}</span>;
          return String(p.value ?? "");
        },
        tooltipValueGetter: (p) => (p.data?.kind === "line" ? p.data.name : undefined),
        cellClass: (p) => (p.data && isEditable(p.data, "name") ? "editable-cell" : "") },
      { colId: "unit", headerName: "Đơn vị", width: 68, editable: (p) => isEditable(p.data, "unit"), cellEditor: TextEditor, valueSetter: commit("unit"),
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.unit : ""),
        cellClass: (p) => (p.data && isEditable(p.data, "unit") ? "editable-cell" : "") },
      ...DIMS.map(([f, h]) => dimCol(f, h)),
      { colId: "quantity", headerName: "Khối lượng", width: 100, type: "rightAligned",
        editable: (p) => isEditable(p.data, "quantity"), cellEditor: TextEditor, valueSetter: commit("quantity"),
        cellEditorParams: { getInitial: (d: TLRow) => editText(d, "quantity") },
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.quantity : p.data?.kind === "detail" ? p.data.d.value ?? null : null),
        cellClass: (p) => `num ${p.data && isEditable(p.data, "quantity") ? "editable-cell" : ""} ${p.data?.kind === "line" && (p.data.line.details ?? []).length ? "calc-cell" : ""}`,
        cellStyle: (p) => (p.data?.kind === "line" ? { fontWeight: 600 } : null),
        tooltipValueGetter: (p) => (p.data?.kind === "line" && (p.data.line.details ?? []).length ? "= tổng các dòng diễn giải bên dưới" : undefined),
        valueFormatter: (p) => (p.value == null ? "" : fmt.qty(p.value as string)) },
      unitCol("unit_vl", "ĐG Vật liệu", 104),
      unitCol("unit_nc", "ĐG Nhân công", 104),
      unitCol("unit_m", "ĐG Máy", 96),
      calcCol("vl", "TT Vật liệu", 116),
      calcCol("nc", "TT Nhân công", 116),
      calcCol("m", "TT Máy", 108),
      { colId: "direct", headerName: "Thành tiền", width: 130, type: "rightAligned", cellClass: "num", pinned: "right",
        cellStyle: { fontWeight: 600 },
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.calc?.direct ?? null : p.data?.kind === "item" ? p.data.total : p.data?.kind === "total" ? p.data.direct : null),
        valueFormatter: money },
      { colId: "warn", headerName: "⚠", width: 46, cellClass: "num", pinned: "right",
        valueGetter: (p) => (p.data?.kind === "line" ? p.data.calc?.warnings.length ?? 0 : null),
        cellRenderer: (p: ICellRendererParams<TLRow>) => {
          if (p.data?.kind !== "line" || !p.data.calc?.warnings.length) return null;
          const blocking = p.data.calc.warnings.some((w) => ["MISSING_PRICE", "WORK_ITEM_NOT_FOUND", "RESOURCE_NOT_FOUND", "QUANTITY_EXPR"].includes(w.code));
          return <span className={blocking ? "err-badge" : "warn-badge"}>{p.data.calc.warnings.length}</span>;
        },
        tooltipValueGetter: (p) => (p.data?.kind === "line" ? p.data.calc?.warnings.map((w) => `• ${w.message}`).join("\n") : undefined) },
    ];
  }, [isEditable, releaseId, showDims, commit, editText]);

  // Excel-style double header: column letters on top, captions below; plus a frozen row-number column.
  const visibleCols = useMemo(() => cols.filter((c) => !c.hide), [cols]);
  const columnDefs = useMemo<(ColDef<TLRow> | ColGroupDef<TLRow>)[]>(() => [
    { headerName: "", children: [{ colId: "rownum", headerName: "", width: 46, pinned: "left", cellClass: "rownum", suppressMovable: true, sortable: false,
      valueGetter: (p) => (p.node?.rowPinned ? "" : (p.node?.rowIndex ?? 0) + 1) }] },
    ...cols.map((c) => ({ headerName: c.hide ? "" : COL_LETTERS[visibleCols.indexOf(c)], headerClass: "ag-header-group-cell-label-center", children: [c] })),
  ], [cols, visibleCols]);

  const letterOf = useCallback((colId: string) => {
    const i = visibleCols.findIndex((c) => c.colId === colId);
    return i >= 0 ? COL_LETTERS[i] : "";
  }, [visibleCols]);

  const onCellFocused = (e: CellFocusedEvent<TLRow>) => {
    const api = apiRef.current;
    if (!api || e.rowIndex === null || !e.column || typeof e.column === "string") { onFocus({ ref: "", text: "", editable: false }); return; }
    const colId = e.column.getColId();
    const row = e.rowPinned ? total : api.getDisplayedRowAtIndex(e.rowIndex)?.data;
    const ref = `${letterOf(colId)}${e.rowPinned ? "Σ" : e.rowIndex + 1}`;
    if (!row) return onFocus({ ref, text: "", editable: false });
    const fieldOf: Record<string, EditableField> = { code: "code", name: "name", unit: "unit", quantity: "quantity", n: "n", l: "l", w: "w", h: "h", ...MANUAL };
    const field = fieldOf[colId];
    const editable = !!field && isEditable(row, colId);
    let text = "";
    let hint: string | undefined;
    if (row.kind === "line") {
      const c = row.calc;
      const formulas: Record<string, string> = {
        vl: c ? `=ROUND(Khối lượng × ĐG VL) = ${fmt.money(c.vl)}` : "", nc: c ? `=ROUND(Khối lượng × ĐG NC × Knc ${row.line.k_nc}) = ${fmt.money(c.nc)}` : "",
        m: c ? `=ROUND(Khối lượng × ĐG Máy × Km ${row.line.k_m}) = ${fmt.money(c.m)}` : "", direct: c ? `=TT VL + TT NC + TT Máy = ${fmt.money(c.direct)}` : "",
        warn: c?.warnings.map((w) => w.message).join(" · ") ?? "", stt: String(row.stt),
      };
      text = field ? editText(row, colId) : formulas[colId] ?? "";
      if (["unit_vl", "unit_nc", "unit_m"].includes(colId)) {
        if (!editable) text = fmt.money(c?.[colId as "unit_vl"] ?? null);
        hint = row.line.work_item ? "Σ hao phí × giá (TT 36/2026, 4.1–4.4) — xem sheet Phân tích vật tư" : "Mã tạm tính: gõ đơn giá (đồng)";
      }
      if (colId === "quantity") hint = (row.line.details ?? []).length ? "Khối lượng = Σ diễn giải (sửa ở các dòng diễn giải)" : "Gõ số, =công thức, hoặc chuột phải → Thêm diễn giải";
    } else if (row.kind === "detail") {
      text = field ? editText(row, colId) : "";
      hint = "Diễn giải: “Chú thích: công thức” · dòng kết thúc “:” là ghi chú · hoặc Số CK × Dài × Rộng × Cao";
    } else if (row.kind === "dghost") { hint = "Gõ diễn giải mới cho công tác phía trên"; }
    else if (row.kind === "item") { text = colId === "direct" ? fmt.money(row.total) : row.name; }
    else if (row.kind === "ghost" || row.kind === "ins") { hint = "Gõ mã đủ (AF.12111) để nhận ngay; gõ đầu mã (AE) hoặc từ khóa (Trát,75) rồi Enter để Tra mã"; }
    else if (row.kind === "total") { text = fmt.money((row as unknown as Record<string, number>)[colId] ?? 0); }
    onFocus({ ref, text, editable, field: row.kind === "item" && colId === "code" ? undefined : field, row, hint });
  };

  const focusedRow = (): TLRow | undefined => {
    const api = apiRef.current;
    const c = api?.getFocusedCell();
    return c && c.rowIndex !== null && !c.rowPinned ? api?.getDisplayedRowAtIndex(c.rowIndex)?.data : undefined;
  };

  useImperativeHandle(ref, () => ({
    focusedRow,
    selectedLines() {
      const api = apiRef.current;
      const sel = (api?.getSelectedRows() ?? []).filter((r): r is Extract<TLRow, { kind: "line" }> => r.kind === "line").map((r) => r.line);
      if (sel.length) return sel;
      const f = focusedRow();
      return f && (f.kind === "line" || f.kind === "detail" || f.kind === "dghost") ? [f.line] : [];
    },
    startInsert(itemId?: number, beforeLineId?: number) {
      if (beforeLineId) {
        const it = revision.items.find((i) => i.lines.some((l) => l.id === beforeLineId));
        if (it) { setInsertAt({ itemId: it.id, beforeLineId }); pendingFocus.current = { rid: "ins", col: "code", edit: true }; return; }
      }
      const api = apiRef.current;
      if (!api) return;
      const target = itemId || focusedRow()?.itemId || revision.items[revision.items.length - 1]?.id;
      const node = target ? api.getRowNode(`g${target}`) : undefined;
      if (node && node.rowIndex !== null) {
        api.ensureIndexVisible(node.rowIndex);
        api.setFocusedCell(node.rowIndex, "code");
        api.startEditingCell({ rowIndex: node.rowIndex, colKey: "code" });
      }
    },
    addDetail(lineId: number) {
      // Chỉ đặt con trỏ vào dòng "＋ diễn giải"; phím đầu tiên gõ vào sẽ mở ô sửa (không mất ký tự)
      setExpanded((s) => new Set(s).add(lineId));
      pendingFocus.current = { rid: `dg${lineId}`, col: "name" };
      const api = apiRef.current;
      const node = api?.getRowNode(`dg${lineId}`);
      if (api && node && node.rowIndex !== null) {
        pendingFocus.current = null;
        api.ensureIndexVisible(node.rowIndex);
        api.setFocusedCell(node.rowIndex, "name");
      }
    },
    focusLine(lineId: number) {
      pendingFocus.current = { rid: `l${lineId}`, col: "quantity" };
    },
  }), [revision.items]); // eslint-disable-line react-hooks/exhaustive-deps

  const onPaste = (e: React.ClipboardEvent) => {
    const api = apiRef.current;
    if (!api || locked || api.getEditingCells().length) return;
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;
    const focused = api.getFocusedCell();
    const row = focused && focused.rowIndex !== null && !focused.rowPinned ? api.getDisplayedRowAtIndex(focused.rowIndex)?.data : undefined;
    const multi = /[\t\n]/.test(text.trim());
    e.preventDefault();
    if (!multi && row && focused) {
      const colId = focused.column.getColId();
      if (isEditable(row, colId)) { void onEdit(row, colId as EditableField, text.trim()); return; }
    }
    const itemId = row?.itemId || revision.items[revision.items.length - 1]?.id;
    if (itemId) {
      if (row?.kind === "ghost") pendingFocus.current = { rid: `g${itemId}`, col: "code" };
      onPasteRows(itemId, text);
    }
  };

  return (
    <div className="sheet" onPaste={onPaste}>
      <AgGridReact<TLRow>
        theme={xlTheme}
        rowData={rows}
        pinnedBottomRowData={[total as TLRow]}
        columnDefs={columnDefs}
        getRowId={(p) => p.data.rid}
        defaultColDef={{ resizable: true, sortable: false, suppressMovable: true, suppressHeaderMenuButton: true, wrapHeaderText: false }}
        getRowClass={(p: RowClassParams<TLRow>) => ({ item: "item-row", ghost: "ghost-row", total: "total-row", detail: "detail-row", dghost: "dghost-row", ins: "ins-row ghost-row", line: "" } as Record<string, string>)[p.data?.kind ?? "line"]}
        rowSelection={{ mode: "multiRow", checkboxes: false, headerCheckbox: false, enableClickSelection: true, isRowSelectable: (n) => n.data?.kind === "line" }}
        groupHeaderHeight={20}
        singleClickEdit={false}
        stopEditingWhenCellsLoseFocus
        enterNavigatesVerticallyAfterEdit
        enterNavigatesVertically
        undoRedoCellEditing={false}
        tooltipShowDelay={300}
        animateRows={false}
        preventDefaultOnContextMenu
        onGridReady={(e) => { apiRef.current = e.api; }}
        onCellFocused={onCellFocused}
        onCellEditingStopped={(e) => { if (e.data?.kind === "ins") window.setTimeout(() => setInsertAt(null), 0); }}
        onCellContextMenu={(e) => {
          const me = e.event as MouseEvent | undefined;
          if (!me) return;
          if (e.rowIndex !== null && e.column && !e.rowPinned) {
            e.api.setFocusedCell(e.rowIndex, e.column);
            if (e.data?.kind === "line" && !e.node.isSelected()) { e.api.deselectAll(); e.node.setSelected(true); }
          }
          onContextMenu(e.rowPinned ? undefined : e.data, me.clientX, me.clientY);
        }}
        onCellKeyDown={(e) => {
          const ke = e.event as KeyboardEvent | undefined;
          if (!ke || !e.data || locked || !("column" in e)) return;
          if (ke.key === "Delete" && !e.api.getEditingCells().length) {
            const colId = e.column.getColId();
            if (isEditable(e.data, colId) && colId !== "code") void onEdit(e.data, colId as EditableField, "");
          }
        }}
      />
    </div>
  );
});

export default TienLuong;
