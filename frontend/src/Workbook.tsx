import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, CONSTRUCTION_TYPES, Detail, Equipment, fmt, Line, Page, Project, Release, Resource, ResourceTotal, Revision, Run, WorkItem } from "./api";
import TienLuong, { EditableField, FocusInfo, normExpr, parseDetailInput, TLHandle, TLRow, viExpr } from "./sheets/TienLuong";
import PhanTich from "./sheets/PhanTich";
import TongHopVatTu from "./sheets/TongHopVatTu";
import TongHopKinhPhi from "./sheets/TongHopKinhPhi";
import TongHopChiPhiXD, { sumEquipment } from "./sheets/TongHopChiPhiXD";
import ChiPhiThietBi from "./sheets/ChiPhiThietBi";
import Bia from "./sheets/Bia";
import TraMa from "./TraMa";
import DataUpdate from "./DataUpdate";
import type { CatalogItem } from "./api";
import { errMsg, Modal, useToast } from "./ui";

type Sheet = "tl" | "pt" | "thvt" | "thkp" | "thxd" | "tb" | "bia";
const SHEETS: [Sheet, string][] = [
  ["tl", "Tiên lượng"], ["pt", "Phân tích vật tư"], ["thvt", "Tổng hợp vật tư"], ["thkp", "Tổng hợp kinh phí"],
  ["thxd", "TH chi phí XD"], ["tb", "Chi phí thiết bị"], ["bia", "Bìa"],
];
const STATUS_VI: Record<string, string> = { draft: "Bản nháp", review: "Đang thẩm định", approved: "Đã phê duyệt", issued: "Đã phát hành" };
const BLOCKING = ["MISSING_PRICE", "WORK_ITEM_NOT_FOUND", "RESOURCE_NOT_FOUND", "QUANTITY_EXPR", "NEGATIVE_QUANTITY", "NEGATIVE_NORM"];
/** Mã đủ (vd AF.12111): không có trong định mức → tạo mã tạm tính. Mã thiếu / từ khóa → mở Tra mã (như G8). */
const FULL_CODE = /^[A-Za-z]{1,3}\.\d{4,6}[A-Za-z]?$/;

/** Accepts "15,5", "15.5", "1.234,5", "1,234.5". */
export function parseNumber(raw: string): number | null {
  let s = raw.trim().replace(/\s/g, "");
  if (!s) return null;
  if (s.includes(",") && s.includes(".")) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, ""); // 1.500.000
  else s = s.replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
const stripValue = (d: Detail): Detail => ({ text: d.text, expr: d.expr, n: d.n, l: d.l, w: d.w, h: d.h });

type InfoForm = {
  name: string; code: string; location: string; investor: string; consultant: string; preparer: string; checker: string;
  construction_type: string; approved_construction_cost_bn: string; vat_rate: string;
  is_remote_area: boolean; is_linear: boolean; is_feasibility_report_only: boolean;
  price_release: number; norm_release: number; region: string; price_period: string;
};
type Dialog =
  | { kind: "item"; mode: "new" | "rename"; itemId?: number; name: string }
  | { kind: "override"; t: ResourceTotal; price: string; reason: string }
  | { kind: "approve"; warnings: { code: string; message: string }[]; reason: string }
  | { kind: "confirm"; title: string; text: string; onOk: () => void }
  | { kind: "trama"; query: string; itemId: number; beforeLineId?: number }
  | { kind: "props"; line: Line; k_nc: string; k_m: string; note: string; manual_vl: string; manual_nc: string; manual_m: string }
  | { kind: "info"; f: InfoForm }
  | { kind: "data" };
type Ctx = { row?: TLRow; x: number; y: number };

export default function Workbook({ projectId, revisionId, onLogout }: { projectId: number; revisionId?: number; onLogout: () => void }) {
  const toast = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [rev, setRev] = useState<Revision | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);
  const [sheet, setSheet] = useState<Sheet>("tl");
  const [ribbon, setRibbon] = useState<"home" | "ct" | "rev" | "help">("home");
  const [focus, setFocus] = useState<FocusInfo>({ ref: "", text: "", editable: false });
  const [barText, setBarText] = useState("");
  const [calcState, setCalcState] = useState<"idle" | "running" | "stale" | "error">("idle");
  const [autoCalc, setAutoCalc] = useState(true);
  const [showDims, setShowDims] = useState(true);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [saving, setSaving] = useState(0);
  const tl = useRef<TLHandle>(null);
  const calcSeq = useRef(0);
  const calcTimer = useRef<number | undefined>(undefined);
  const clip = useRef<{ tsv: string; lines: Line[] } | null>(null);
  const seededItem = useRef<Set<number>>(new Set());

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { onLogout(); return; }
    toast(errMsg(e), true);
  }, [onLogout, toast]);

  // ------------------------------------------------------------- loading
  const loadRun = useCallback(async (rid: number) => {
    const list = await api.get<Page<Run>>("/calculation-runs", { revision: rid, status: "done" });
    if (!list.results.length) { setRun(null); return null; }
    const detail = await api.get<Run>(`/calculation-runs/${list.results[0].id}`);
    setRun(detail);
    return detail;
  }, []);

  const loadRevision = useCallback(async (rid: number) => {
    const r = await api.get<Revision>(`/revisions/${rid}`);
    r.items.forEach((it) => it.lines.forEach((l) => latestLine.current.set(l.id, l)));
    setRev(r);
    return r;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [p, revs, rels] = await Promise.all([
          api.get<Project>(`/projects/${projectId}`),
          api.get<Revision[]>(`/projects/${projectId}/revisions`),
          api.get<Page<Release>>("/catalog/releases"),
        ]);
        setProject(p); setReleases(rels.results);
        let list = revs;
        if (!list.length) { await api.post(`/projects/${projectId}/revisions`, { title: "Dự toán lần 1" }); list = await api.get<Revision[]>(`/projects/${projectId}/revisions`); }
        setRevisions(list);
        const target = list.find((r) => r.id === revisionId) ?? list[list.length - 1];
        const r = await loadRevision(target.id);
        const lastRun = await loadRun(target.id);
        const hasLines = r.items.some((i) => i.lines.length);
        if (hasLines && !lastRun) scheduleRecalc(0);
        if (!r.items.length && !r.is_locked && !seededItem.current.has(r.id)) {
          seededItem.current.add(r.id);
          await api.post(`/revisions/${r.id}/items`, { name: "Hạng mục 1", order: 1 });
          await loadRevision(r.id);
        }
      } catch (e) { fail(e); }
    })();
    return () => window.clearTimeout(calcTimer.current);
  }, [projectId, revisionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------- calculation
  const recalc = useCallback(async () => {
    if (!rev) return;
    const seq = ++calcSeq.current;
    setCalcState("running");
    try {
      const r = await api.post<Run>(`/revisions/${rev.id}/calculate`);
      if (seq !== calcSeq.current) return;
      if (r.status !== "done") {
        // large revision → Celery job; poll
        for (let i = 0; i < 60 && seq === calcSeq.current; i++) {
          await new Promise((res) => setTimeout(res, 1000));
          const s = await api.get<Run>(`/calculation-runs/${r.id}`);
          if (s.status === "done") { setRun(s); setCalcState("idle"); return; }
          if (s.status === "failed") throw new Error(s.error || "Tính toán lỗi");
        }
        return;
      }
      const detail = await api.get<Run>(`/calculation-runs/${r.id}`);
      if (seq === calcSeq.current) { setRun(detail); setCalcState("idle"); }
    } catch (e) { if (seq === calcSeq.current) setCalcState("error"); fail(e); }
  }, [rev, fail]);

  const recalcRef = useRef(recalc);
  recalcRef.current = recalc;
  const scheduleRecalc = useCallback((delay = 450) => {
    setCalcState("stale");
    window.clearTimeout(calcTimer.current);
    calcTimer.current = window.setTimeout(() => { void recalcRef.current(); }, delay);
  }, []);

  const afterChange = useCallback(() => { if (autoCalc) scheduleRecalc(); else setCalcState("stale"); }, [autoCalc, scheduleRecalc]);

  // ------------------------------------------------------------- mutations
  const replaceLine = (line: Line) => setRev((r) => r && ({ ...r, items: r.items.map((it) => it.id === line.item ? { ...it, lines: it.lines.some((l) => l.id === line.id) ? it.lines.map((l) => (l.id === line.id ? line : l)) : [...it.lines, line] } : it) }));

  const resolveCode = useCallback(async (code: string): Promise<WorkItem | null> => {
    if (!project || !code.trim()) return null;
    const r = await api.get<Page<WorkItem>>("/catalog/work-items", { query: code.trim(), release: project.norm_release });
    return r.results.find((w) => w.code.toLowerCase() === code.trim().toLowerCase()) ?? null;
  }, [project]);

  const track = async <T,>(p: Promise<T>): Promise<T> => { setSaving((n) => n + 1); try { return await p; } finally { setSaving((n) => n - 1); } };

  const nextOrder = (itemId: number) => Math.max(0, ...(rev?.items.find((i) => i.id === itemId)?.lines.map((l) => l.order) ?? [0])) + 1;
  const itemName = (itemId: number) => rev?.items.find((i) => i.id === itemId)?.name ?? "";

  /** Tạo nhiều dòng; nếu có beforeLineId thì chèn lên trên dòng đó (G8: Insert chèn dòng lên trên). */
  const insertLines = useCallback(async (itemId: number, bodies: Record<string, unknown>[], beforeLineId?: number) => {
    if (!rev || !bodies.length) return [] as Line[];
    let order = nextOrder(itemId);
    const created = await track(api.post<Line[]>(`/revisions/${rev.id}/lines`, bodies.map((b) => ({ item: itemId, order: order++, ...b }))));
    if (beforeLineId) {
      const ids = [...(rev.items.find((i) => i.id === itemId)?.lines ?? [])].sort((a, b) => a.order - b.order || a.id - b.id).map((l) => l.id);
      const at = Math.max(0, ids.indexOf(beforeLineId));
      ids.splice(at, 0, ...created.map((l) => l.id));
      await track(api.post(`/revisions/${rev.id}/items/${itemId}/reorder`, { line_ids: ids }));
      await loadRevision(rev.id);
    } else created.forEach(replaceLine);
    afterChange();
    return created;
  }, [rev, afterChange, loadRevision]); // eslint-disable-line react-hooks/exhaustive-deps

  const createLine = useCallback(async (itemId: number, code: string, beforeLineId?: number) => {
    if (!rev) return;
    const c = code.trim();
    const wi = await resolveCode(c);
    if (!wi && !FULL_CODE.test(c)) { setDialog({ kind: "trama", query: c, itemId, beforeLineId }); return; }
    const body = wi ? { work_item: wi.id } : { custom_code: c, name: "(Công tác tạm tính — nhập tên)", unit: "đv" };
    const [line] = await insertLines(itemId, [body], beforeLineId);
    if (!wi) toast(`Mã "${c}" không có trong bộ định mức → mã tạm tính. Nhập tên, đơn vị và đơn giá VL/NC/M.`, true);
    if (line) tl.current?.focusLine(line.id);
  }, [rev, resolveCode, insertLines, toast]);

  // Lưu theo hàng đợi từng dòng: gõ nhanh nhiều ô (Dài → Tab → Rộng…) không gây xung đột version / ghi đè diễn giải
  const latestLine = useRef(new Map<number, Line>());
  const lineQueue = useRef(new Map<number, Promise<unknown>>());
  const freshLine = (l: Line) => { const x = latestLine.current.get(l.id); return x && x.version >= l.version ? x : l; };

  const patchLine = useCallback((line: Line, body: Record<string, unknown> | ((cur: Line) => Record<string, unknown> | null)) => {
    if (!rev) return Promise.resolve();
    const prev = lineQueue.current.get(line.id) ?? Promise.resolve();
    const job = prev.catch(() => undefined).then(async () => {
      const cur = freshLine(line);
      const b = typeof body === "function" ? body(cur) : body;
      if (!b) return;
      try {
        const updated = await track(api.patch<Line>(`/revisions/${rev.id}/lines/${line.id}`, { ...b, version: cur.version }));
        latestLine.current.set(updated.id, updated);
        replaceLine(updated);
        afterChange();
      } catch (e) {
        latestLine.current.delete(line.id);
        if (e instanceof ApiError && e.status === 409) { toast("Dòng vừa được người khác sửa — đã tải lại.", true); await loadRevision(rev.id); return; }
        await loadRevision(rev.id);
        throw e;
      }
    });
    lineQueue.current.set(line.id, job);
    return job;
  }, [rev, afterChange, loadRevision, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Sửa / thêm / xóa một dòng diễn giải khối lượng (tính trên bản mới nhất của dòng). */
  const editDetail = useCallback(async (row: Extract<TLRow, { kind: "detail" | "dghost" }>, field: EditableField, value: string) => {
    let dim: string | null = null;
    if (field === "n" || field === "l" || field === "w" || field === "h") {
      const n = value.trim() ? parseNumber(value) : null;
      if (value.trim() && n === null) { toast(`"${value}" không phải số`, true); return; }
      dim = n === null ? null : String(n);
    } else if (field !== "name" && field !== "quantity") return;
    await patchLine(row.line, (cur) => {
      const list = (cur.details ?? []).map(stripValue);
      const isNew = row.kind === "dghost";
      const idx = isNew ? list.length : row.idx;
      if (!isNew && !list[idx]) return null;
      const d: Detail = isNew ? { text: "", expr: "", n: null, l: null, w: null, h: null } : { ...list[idx] };
      if (field === "name") { const p = parseDetailInput(value); d.text = p.text; d.expr = p.expr; }
      else if (field === "quantity") d.expr = value.trim() ? normExpr(value) : "";
      else d[field as "n" | "l" | "w" | "h"] = dim;
      const empty = !d.text && !d.expr && d.n == null && d.l == null && d.w == null && d.h == null;
      if (isNew) { if (empty) return null; list.push(d); }
      else if (empty) list.splice(idx, 1);
      else list[idx] = d;
      return { details: list };
    });
  }, [patchLine, toast]);

  const onEdit = useCallback(async (row: TLRow, field: EditableField | "item_name", value: string) => {
    if (!rev) return;
    try {
      if (row.kind === "item" && field === "item_name") {
        if (!value.trim() || value === row.name) return;
        await track(api.patch(`/revisions/${rev.id}/items/${row.itemId}`, { name: value.trim() }));
        await loadRevision(rev.id);
        return;
      }
      if ((row.kind === "ghost" || row.kind === "ins") && field === "code") {
        if (value.trim()) await createLine(row.itemId, value, row.kind === "ins" ? row.beforeLineId : undefined);
        return;
      }
      if ((row.kind === "detail" || row.kind === "dghost") && field !== "item_name") { await editDetail(row, field, value); return; }
      if (row.kind !== "line") return;
      const line = row.line;
      if (field === "code") {
        const wi = await resolveCode(value);
        if (wi) await patchLine(line, { work_item: wi.id, custom_code: "", name: wi.name, unit: wi.unit });
        else if (!FULL_CODE.test(value.trim())) setDialog({ kind: "trama", query: value.trim(), itemId: row.itemId, beforeLineId: line.id });
        else { await patchLine(line, { work_item: null, custom_code: value.trim(), name: line.name, unit: line.unit }); toast(`Mã "${value}" không có trong bộ định mức → mã tạm tính`, true); }
      } else if (field === "name" || field === "unit") {
        if (value.trim()) await patchLine(line, { [field]: value.trim() });
      } else if (field === "quantity") {
        if (value.trim().startsWith("=")) await patchLine(line, { quantity_expr: normExpr(value) });
        else if (!value.trim()) await patchLine(line, { quantity: "0", quantity_expr: "" });
        else {
          const n = parseNumber(value);
          if (n === null) { toast(`"${value}" không phải số. Gõ số hoặc =công thức`, true); await loadRevision(rev.id); return; }
          await patchLine(line, { quantity: String(n), quantity_expr: "" });
        }
      } else if (field === "manual_vl" || field === "manual_nc" || field === "manual_m") {
        const n = value.trim() ? parseNumber(value) : null;
        if (value.trim() && (n === null || n < 0)) { toast(`"${value}" không phải đơn giá hợp lệ`, true); return; }
        await patchLine(line, { [field]: n === null ? null : String(Math.round(n)) });
      }
    } catch (e) { fail(e); }
  }, [rev, createLine, patchLine, editDetail, resolveCode, loadRevision, fail, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  const insertWorkItems = async (wis: WorkItem[], itemId: number, beforeLineId?: number) => {
    setDialog(null);
    try {
      const created = await insertLines(itemId, wis.map((w) => ({ work_item: w.id })), beforeLineId);
      toast(`Đã chèn ${created.length} công tác vào “${itemName(itemId)}”. Nhập khối lượng hoặc diễn giải.`);
      if (created[0]) tl.current?.focusLine(created[0].id);
    } catch (e) { fail(e); }
  };

  // ------------------------------------------------------------- copy / paste công tác (kèm diễn giải, đơn giá tạm tính)
  const copyLines = () => {
    const lines = tl.current?.selectedLines() ?? [];
    if (!lines.length) return toast("Chọn dòng công tác để sao chép (Ctrl/Shift + click để chọn nhiều)", true);
    const tsv = lines.map((l) => [l.code, l.name, l.unit, l.quantity_expr ? `=${viExpr(l.quantity_expr)}` : fmt.qty(l.quantity, 6)].join("\t")).join("\n");
    clip.current = { tsv, lines };
    navigator.clipboard?.writeText(tsv).catch(() => undefined);
    toast(`Đã sao chép ${lines.length} công tác — chọn vị trí rồi Ctrl+V (dán lên trên dòng đang chọn)`);
  };

  const pasteClip = async (itemId: number, beforeLineId?: number) => {
    const c = clip.current;
    if (!c) return;
    const bodies = c.lines.map((l) => ({
      work_item: l.work_item, custom_code: l.work_item ? "" : l.custom_code, name: l.name, unit: l.unit,
      quantity_expr: l.quantity_expr, quantity: l.quantity, k_nc: l.k_nc, k_m: l.k_m, note: l.note,
      details: (l.details ?? []).map(stripValue), manual_vl: l.manual_vl, manual_nc: l.manual_nc, manual_m: l.manual_m,
    }));
    try {
      const created = await insertLines(itemId, bodies, beforeLineId);
      toast(`Đã dán ${created.length} công tác (kèm diễn giải khối lượng)`);
    } catch (e) { fail(e); }
  };

  /** Paste rows copied from Excel: find a norm code (AB.12345) and a quantity in each row. */
  const onPasteRows = useCallback(async (itemId: number, text: string) => {
    if (!rev) return;
    const norm = (s: string) => s.replace(/\r/g, "").trim();
    const focused = tl.current?.focusedRow();
    const before = focused?.kind === "line" && focused.itemId === itemId ? focused.line.id : undefined;
    if (clip.current && norm(text) === norm(clip.current.tsv)) { await pasteClip(itemId, before); return; }
    const rows = text.replace(/\r/g, "").split("\n").map((r) => r.split("\t").map((c) => c.trim())).filter((r) => r.some(Boolean));
    const bodies: Record<string, unknown>[] = [];
    try {
      setSaving((n) => n + 1);
      for (const cells of rows) {
        const code = cells.find((c) => /^[A-Za-z]{1,3}\.\d[\w.]*$/.test(c));
        const numeric = cells.filter((c) => c !== code && parseNumber(c) !== null);
        const qtyCell = numeric[numeric.length - 1];
        const expr = cells.find((c) => c.startsWith("=") || /^[\d.,\s()+\-*/x×]+$/.test(c) && /[*/x×+]/.test(c));
        const texts = cells.filter((c) => c && c !== code && parseNumber(c) === null && c !== expr);
        const name = texts.sort((a, b) => b.length - a.length)[0] ?? "";
        const unit = texts.find((t) => t !== name && t.length <= 8) ?? "";
        if (!code && !name) continue;
        const wi = code ? await resolveCode(code) : null;
        const body: Record<string, unknown> = {};
        if (wi) body.work_item = wi.id;
        else Object.assign(body, { custom_code: code ?? "TT", name: name || "(Công tác tạm tính)", unit: unit || "đv" });
        if (expr) body.quantity_expr = normExpr(expr);
        else if (qtyCell) body.quantity = String(parseNumber(qtyCell));
        bodies.push(body);
      }
    } finally { setSaving((n) => n - 1); }
    if (!bodies.length) { toast("Không nhận ra dòng nào. Cần có mã hiệu (vd AF.12111) hoặc tên công tác.", true); return; }
    try { await insertLines(itemId, bodies, before); toast(`Đã dán ${bodies.length} dòng công tác`); } catch (e) { fail(e); }
  }, [rev, resolveCode, insertLines, fail, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------- delete / move / properties
  const deleteSelection = () => {
    if (!rev) return;
    const row = tl.current?.focusedRow();
    if (row?.kind === "detail") { removeDetail(row); return; }
    if (row?.kind === "item") return deleteItem(row.itemId);
    const lines = tl.current?.selectedLines() ?? [];
    if (!lines.length) return toast("Chọn dòng công tác để xóa", true);
    const text = lines.length === 1 ? `Xóa dòng ${lines[0].code} — ${lines[0].name}?` : `Xóa ${lines.length} dòng công tác đã chọn?`;
    setDialog({ kind: "confirm", title: "Xóa dòng công tác", text, onOk: async () => {
      try { for (const l of lines) await track(api.del(`/revisions/${rev.id}/lines/${l.id}`)); await loadRevision(rev.id); afterChange(); } catch (e) { fail(e); }
    } });
  };
  const removeDetail = (row: Extract<TLRow, { kind: "detail" }>) => {
    void patchLine(row.line, (cur) => {
      const list = (cur.details ?? []).map(stripValue);
      if (!list[row.idx]) return null;
      list.splice(row.idx, 1);
      return { details: list };
    }).catch(fail);
  };

  const moveLine = async (dir: -1 | 1) => {
    if (!rev) return;
    const [line] = tl.current?.selectedLines() ?? [];
    if (!line) return toast("Chọn dòng công tác cần di chuyển", true);
    const item = rev.items.find((i) => i.id === line.item);
    if (!item) return;
    const ids = [...item.lines].sort((a, b) => a.order - b.order || a.id - b.id).map((l) => l.id);
    const i = ids.indexOf(line.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    try { await track(api.post(`/revisions/${rev.id}/items/${item.id}/reorder`, { line_ids: ids })); await loadRevision(rev.id); tl.current?.focusLine(line.id); } catch (e) { fail(e); }
  };

  const openProps = (line?: Line) => {
    const l = line ?? (tl.current?.selectedLines() ?? [])[0];
    if (!l) return toast("Chọn một dòng công tác", true);
    const m = (v: string | null) => (v == null ? "" : fmt.money(v));
    setDialog({ kind: "props", line: l, k_nc: fmt.qty(l.k_nc, 4), k_m: fmt.qty(l.k_m, 4), note: l.note, manual_vl: m(l.manual_vl), manual_nc: m(l.manual_nc), manual_m: m(l.manual_m) });
  };
  const saveProps = async (d: Extract<Dialog, { kind: "props" }>) => {
    const knc = parseNumber(d.k_nc), km = parseNumber(d.k_m);
    if (knc === null || km === null || knc <= 0 || km <= 0) return toast("Hệ số Knc, Km phải là số dương", true);
    const money = (s: string) => (s.trim() ? parseNumber(s) : null);
    const mv = money(d.manual_vl), mn = money(d.manual_nc), mm = money(d.manual_m);
    if ([d.manual_vl, d.manual_nc, d.manual_m].some((s, i) => s.trim() && [mv, mn, mm][i] === null)) return toast("Đơn giá tạm tính không hợp lệ", true);
    try {
      await patchLine(d.line, { k_nc: String(knc), k_m: String(km), note: d.note, manual_vl: mv === null ? null : String(Math.round(mv)), manual_nc: mn === null ? null : String(Math.round(mn)), manual_m: mm === null ? null : String(Math.round(mm)) });
      setDialog(null);
    } catch (e) { fail(e); }
  };

  const deleteItem = (itemId: number) => {
    if (!rev) return;
    const it = rev.items.find((i) => i.id === itemId);
    if (!it) return;
    setDialog({ kind: "confirm", title: "Xóa hạng mục", text: `Xóa hạng mục "${it.name}" và ${it.lines.length} dòng công tác bên trong?`, onOk: async () => {
      try { await track(api.del(`/revisions/${rev.id}/items/${itemId}`)); await loadRevision(rev.id); afterChange(); } catch (e) { fail(e); }
    } });
  };

  const saveItemDialog = async (d: Extract<Dialog, { kind: "item" }>) => {
    if (!rev || !d.name.trim()) return;
    try {
      if (d.mode === "new") {
        const order = Math.max(0, ...rev.items.map((i) => i.order)) + 1;
        const it = await track(api.post<{ id: number }>(`/revisions/${rev.id}/items`, { name: d.name.trim(), order }));
        await loadRevision(rev.id);
        setTimeout(() => tl.current?.startInsert(it.id), 50);
      } else if (d.itemId) {
        await track(api.patch(`/revisions/${rev.id}/items/${d.itemId}`, { name: d.name.trim() }));
        await loadRevision(rev.id);
      }
      setDialog(null);
    } catch (e) { fail(e); }
  };

  const saveOverride = async (d: Extract<Dialog, { kind: "override" }>) => {
    if (!rev) return;
    const n = parseNumber(d.price);
    if (n === null || n < 0) return toast("Đơn giá không hợp lệ", true);
    if (!d.reason.trim()) return toast("Cần ghi lý do / nguồn giá", true);
    try {
      const res = await api.get<Page<Resource>>("/catalog/resources", { query: d.t.resource_code });
      const r = res.results.find((x) => x.code === d.t.resource_code);
      if (!r) throw new Error(`Không tìm thấy nguồn lực ${d.t.resource_code}`);
      await track(api.post(`/revisions/${rev.id}/overrides`, { resource: r.id, price: String(Math.round(n)), reason: d.reason.trim() }));
      setDialog(null);
      await loadRevision(rev.id);
      scheduleRecalc(0);
    } catch (e) { fail(e); }
  };

  // ------------------------------------------------------------- thông tin công trình
  const openInfo = () => {
    if (!project) return;
    const p = project;
    setDialog({ kind: "info", f: {
      name: p.name, code: p.code, location: p.location, investor: p.investor ?? "", consultant: p.consultant ?? "", preparer: p.preparer ?? "", checker: p.checker ?? "",
      construction_type: p.construction_type, approved_construction_cost_bn: p.approved_construction_cost_bn ?? "", vat_rate: p.vat_rate ? String(Number(p.vat_rate) * 100) : "",
      is_remote_area: p.is_remote_area, is_linear: p.is_linear, is_feasibility_report_only: p.is_feasibility_report_only,
      price_release: p.price_release, norm_release: p.norm_release, region: p.region, price_period: p.price_period,
    } });
  };
  const saveInfo = async (f: InfoForm) => {
    if (!project || !f.name.trim()) return toast("Cần tên công trình", true);
    const vat = f.vat_rate.trim() ? parseNumber(f.vat_rate) : null;
    if (f.vat_rate.trim() && (vat === null || vat < 0 || vat > 100)) return toast("Thuế GTGT (%) không hợp lệ", true);
    const tm = f.approved_construction_cost_bn.trim() ? parseNumber(f.approved_construction_cost_bn) : null;
    try {
      const p = await track(api.patch<Project>(`/projects/${project.id}`, {
        ...f, approved_construction_cost_bn: tm === null ? null : String(tm), vat_rate: vat === null ? null : String(vat / 100),
      }));
      setProject(p);
      setDialog(null);
      toast("Đã lưu thông tin công trình");
      if (!rev?.is_locked) scheduleRecalc(0);
    } catch (e) { fail(e); }
  };

  // ------------------------------------------------------------- chi phí thiết bị
  const eqAdd = async (name: string) => {
    if (!rev) return;
    try { await track(api.post<Equipment>(`/revisions/${rev.id}/equipment`, { name, order: (rev.equipment?.length ?? 0) + 1 })); await loadRevision(rev.id); } catch (e) { fail(e); }
  };
  const eqSave = async (e: Equipment, body: Record<string, string>) => {
    if (!rev) return;
    try { await track(api.patch(`/revisions/${rev.id}/equipment/${e.id}`, body)); await loadRevision(rev.id); } catch (err) { fail(err); await loadRevision(rev.id); }
  };
  const eqDelete = (e: Equipment) => {
    if (!rev) return;
    setDialog({ kind: "confirm", title: "Xóa thiết bị", text: `Xóa “${e.name}”?`, onOk: async () => {
      try { await track(api.del(`/revisions/${rev.id}/equipment/${e.id}`)); await loadRevision(rev.id); } catch (err) { fail(err); }
    } });
  };

  // ------------------------------------------------------------- duyệt / phiên bản / xuất
  const approve = async (force = false, reason = "") => {
    if (!rev) return;
    try {
      if (calcState !== "idle") await recalc();
      const r = await track(api.post<Revision>(`/revisions/${rev.id}/approve`, { force, reason }));
      setRev((old) => old && { ...old, ...r });
      setRevisions((list) => list.map((x) => (x.id === r.id ? { ...x, status: r.status } : x)));
      setDialog(null);
      toast("Đã phê duyệt và khóa bản dự toán");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.data && typeof e.data === "object" && "warnings" in e.data) {
        setDialog({ kind: "approve", warnings: (e.data as { warnings: { code: string; message: string }[] }).warnings, reason: "" });
      } else fail(e);
    }
  };

  const sendReview = async () => {
    if (!rev) return;
    try { const r = await track(api.post<Revision>(`/revisions/${rev.id}/review`)); setRev((o) => o && { ...o, status: r.status }); toast("Đã chuyển sang thẩm định"); } catch (e) { fail(e); }
  };

  const newRevisionFrom = async () => {
    if (!rev) return;
    try {
      const r = await track(api.post<Revision>(`/projects/${projectId}/revisions`, { title: `Dự toán lần ${revisions.length + 1}`, copy_from: rev.id }));
      window.location.hash = `#/p/${projectId}/r/${r.id}`;
    } catch (e) { fail(e); }
  };

  const exportXlsx = async () => {
    if (!rev) return;
    try {
      if (calcState !== "idle") await recalc();
      const { blob, filename } = await track(api.download(`/revisions/${rev.id}/export?template=estimate-xlsx`));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast(`Đã xuất ${filename}`);
    } catch (e) { fail(e); }
  };

  // ------------------------------------------------------------- actions shared by ribbon, context menu, keys
  const locked = !!rev?.is_locked;
  const focusedLineId = () => { const r = tl.current?.focusedRow(); return r?.kind === "line" ? r.line.id : undefined; };
  const focusedItemId = () => tl.current?.focusedRow()?.itemId || rev?.items[rev.items.length - 1]?.id;
  const actInsert = () => { setSheet("tl"); setTimeout(() => tl.current?.startInsert(focusedItemId(), focusedLineId()), 0); };
  const actTraMa = () => { const itemId = focusedItemId(); if (itemId) setDialog({ kind: "trama", query: "", itemId, beforeLineId: focusedLineId() }); };
  const actDetail = () => {
    const r = tl.current?.focusedRow();
    const lineId = r && (r.kind === "line" || r.kind === "detail" || r.kind === "dghost") ? r.line.id : undefined;
    if (!lineId) return toast("Chọn dòng công tác cần diễn giải khối lượng", true);
    tl.current?.addDetail(lineId);
  };

  // ------------------------------------------------------------- keyboard shortcuts (theo G8: Insert, F8, F3…)
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (dialog) return;
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT");
      if (e.key === "F9") { e.preventDefault(); void recalc(); return; }
      if (sheet !== "tl" || typing) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && !window.getSelection()?.toString()) { e.preventDefault(); copyLines(); return; }
      if (locked) return;
      if (e.key === "Insert") { e.preventDefault(); actInsert(); }
      else if (e.key === "F8" || ((e.ctrlKey || e.metaKey) && e.key === "-")) { e.preventDefault(); deleteSelection(); }
      else if (e.key === "F3") { e.preventDefault(); actTraMa(); }
      else if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); void moveLine(-1); }
      else if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); void moveLine(1); }
      else if (e.altKey && e.key.toLowerCase() === "d") { e.preventDefault(); actDetail(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  useEffect(() => {
    if (!ctx) return;
    const close = () => setCtx(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", onKey); window.removeEventListener("resize", close); };
  }, [ctx]);

  useEffect(() => { setBarText(focus.text); }, [focus]);

  const commitBar = async () => {
    if (!focus.editable || !focus.row || !focus.field || barText === focus.text) return;
    await onEdit(focus.row, focus.field, barText);
  };

  // ------------------------------------------------------------- derived
  const sample = useMemo(() => !!project && releases.some((r) => r.is_sample && (r.id === project.norm_release || r.id === project.price_release)), [project, releases]);
  const values = run?.result?.summary.values;
  const blocking = run?.warnings.filter((w) => BLOCKING.includes(w.code)).length ?? 0;
  const otherWarn = (run?.warnings.length ?? 0) - blocking;
  const lineCount = rev?.items.reduce((s, i) => s + i.lines.length, 0) ?? 0;
  const eqTotal = sumEquipment(rev?.equipment ?? []).after;

  if (!project || !rev) return (<><div className="titlebar"><div className="logo">SE</div><div className="doc">Đang mở…</div></div><div className="page" /></>);

  const ctxRow = ctx?.row;
  const ctxLine = ctxRow && (ctxRow.kind === "line" || ctxRow.kind === "detail" || ctxRow.kind === "dghost") ? ctxRow.line : undefined;
  const run_ = (fn: () => void) => () => { setCtx(null); fn(); };

  return (
    <>
      <div className="titlebar">
        <div className="logo">SE</div>
        <button className="link" style={{ color: "#fff" }} onClick={() => (window.location.hash = "")} title="Về danh sách công trình">← Công trình</button>
        <div className="doc">{project.name} — {rev.title || `Dự toán lần ${rev.number}`} ({STATUS_VI[rev.status]}){saving > 0 ? " · Đang lưu…" : " · Đã lưu"}</div>
        <div className="user"><button className="link" onClick={onLogout}>Đăng xuất</button></div>
      </div>

      <div className="ribbon-tabs" role="tablist">
        <button className={ribbon === "home" ? "active" : ""} onClick={() => setRibbon("home")}>Trang chủ</button>
        <button className={ribbon === "ct" ? "active" : ""} onClick={() => setRibbon("ct")}>Công trình</button>
        <button className={ribbon === "rev" ? "active" : ""} onClick={() => setRibbon("rev")}>Phiên bản & duyệt</button>
        <button className={ribbon === "help" ? "active" : ""} onClick={() => setRibbon("help")}>Hướng dẫn</button>
      </div>

      {ribbon === "home" && (
        <div className="ribbon">
          <div className="rgroup"><div className="btns">
            <button className="rbtn" onClick={() => setDialog({ kind: "item", mode: "new", name: `Hạng mục ${rev.items.length + 1}` })} disabled={locked}><span className="ico">🗂️</span>Thêm<br />hạng mục</button>
            <div className="rstack">
              <button className="rbtn" disabled={locked} onClick={() => { const r = tl.current?.focusedRow(); const it = rev.items.find((i) => i.id === r?.itemId); if (it) setDialog({ kind: "item", mode: "rename", itemId: it.id, name: it.name }); else toast("Chọn một ô trong hạng mục", true); }}><span className="ico">✏️</span>Đổi tên</button>
              <button className="rbtn" disabled={locked} onClick={() => { const r = tl.current?.focusedRow(); if (r?.itemId) deleteItem(r.itemId); else toast("Chọn một ô trong hạng mục", true); }}><span className="ico">🗑️</span>Xóa hạng mục</button>
            </div>
          </div><div className="label">Hạng mục</div></div>

          <div className="rgroup"><div className="btns">
            <button className="rbtn primary" onClick={actInsert} disabled={locked}><span className="ico">➕</span>Chèn dòng<br />(Insert)</button>
            <button className="rbtn primary" onClick={() => { setSheet("tl"); actTraMa(); }} disabled={locked}><span className="ico">🔎</span>Tra mã<br />(F3)</button>
            <div className="rstack">
              <button className="rbtn" onClick={actDetail} disabled={locked || sheet !== "tl"}><span className="ico">📐</span>Diễn giải KL (Alt+D)</button>
              <button className="rbtn" onClick={() => openProps()} disabled={locked || sheet !== "tl"}><span className="ico">⚙️</span>Hệ số / giá tạm tính</button>
              <button className="rbtn" onClick={deleteSelection} disabled={locked || sheet !== "tl"}><span className="ico">➖</span>Xóa dòng (F8)</button>
            </div>
          </div><div className="label">Công tác</div></div>

          <div className="rgroup"><div className="btns">
            <div className="rstack">
              <button className="rbtn" onClick={copyLines} disabled={sheet !== "tl"}><span className="ico">📋</span>Sao chép (Ctrl+C)</button>
              <button className="rbtn" onClick={() => { const it = focusedItemId(); if (it) void pasteClip(it, focusedLineId()); }} disabled={locked || sheet !== "tl" || !clip.current}><span className="ico">📌</span>Dán công tác</button>
            </div>
            <div className="rstack">
              <button className="rbtn" onClick={() => void moveLine(-1)} disabled={locked || sheet !== "tl"}><span className="ico">⬆️</span>Lên (Alt+↑)</button>
              <button className="rbtn" onClick={() => void moveLine(1)} disabled={locked || sheet !== "tl"}><span className="ico">⬇️</span>Xuống (Alt+↓)</button>
            </div>
          </div><div className="label">Sao chép & sắp xếp</div></div>

          <div className="rgroup"><div className="btns">
            <div className="rstack">
              <label className="rbtn" style={{ cursor: "pointer" }}><input type="checkbox" checked={showDims} onChange={(e) => setShowDims(e.target.checked)} /> Cột Số CK / Dài / Rộng / Cao</label>
              <label className="rbtn" style={{ cursor: "pointer" }}><input type="checkbox" checked={autoCalc} onChange={(e) => setAutoCalc(e.target.checked)} /> Tự động tính</label>
            </div>
            <button className="rbtn primary" onClick={() => void recalc()}><span className="ico">🧮</span>Tính lại<br />(F9)</button>
          </div><div className="label">Hiển thị & tính</div></div>

          <div className="rgroup"><div className="btns">
            <button className="rbtn primary" onClick={exportXlsx} disabled={!lineCount}><span className="ico">📥</span>Xuất<br />Excel</button>
          </div><div className="label">Hồ sơ</div></div>

          <div className="rgroup"><div className="btns">
            <button className="rbtn" onClick={sendReview} disabled={locked || rev.status === "review"}><span className="ico">📨</span>Gửi<br />thẩm định</button>
            <button className="rbtn" onClick={() => approve()} disabled={locked || !lineCount}><span className="ico">✅</span>Phê duyệt<br />& khóa</button>
          </div><div className="label">Duyệt</div></div>
        </div>
      )}
      {ribbon === "ct" && (
        <div className="ribbon">
          <div className="rgroup"><div className="btns">
            <button className="rbtn primary" onClick={openInfo}><span className="ico">🏗️</span>Thông tin<br />công trình</button>
            <button className="rbtn" onClick={openInfo}><span className="ico">💲</span>Bộ giá /<br />kỳ giá</button>
          </div><div className="label">Công trình</div></div>
          <div className="rgroup"><div className="btns">
            <button className="rbtn primary" onClick={() => setDialog({ kind: "data" })}><span className="ico">🔄</span>Cập nhật<br />dữ liệu</button>
          </div><div className="label">Định mức & giá</div></div>
          <div className="rgroup"><div className="btns">
            <button className="rbtn" onClick={() => setSheet("thkp")}><span className="ico">📊</span>THKP<br />hạng mục</button>
            <button className="rbtn" onClick={() => setSheet("thxd")}><span className="ico">🧾</span>TH chi phí<br />xây dựng</button>
            <button className="rbtn" onClick={() => setSheet("tb")}><span className="ico">🔧</span>Chi phí<br />thiết bị</button>
            <button className="rbtn" onClick={() => setSheet("bia")}><span className="ico">📘</span>Bìa<br />hồ sơ</button>
          </div><div className="label">Bảng tổng hợp</div></div>
          <div className="rgroup" style={{ justifyContent: "center", fontSize: 12, color: "#444", maxWidth: 420 }}>
            <div>Chủ đầu tư: <b>{project.investor || "—"}</b></div>
            <div>Địa điểm: {project.location || "—"} · Loại: {CONSTRUCTION_TYPES.find((c) => c[0] === project.construction_type)?.[1]}</div>
            <div>Bộ giá: {releases.find((r) => r.id === project.price_release)?.name ?? "—"} · {project.region} · {project.price_period}</div>
          </div>
        </div>
      )}
      {ribbon === "rev" && (
        <div className="ribbon">
          <div className="rgroup"><div className="btns" style={{ flexWrap: "wrap", maxWidth: 680 }}>
            {revisions.map((r) => (
              <button key={r.id} className="rbtn" style={r.id === rev.id ? { background: "#dff0e6", borderColor: "#217346" } : {}} onClick={() => (window.location.hash = `#/p/${projectId}/r/${r.id}`)}>
                <span className="ico">{r.is_locked ? "🔒" : "📝"}</span>{r.title || `Lần ${r.number}`}<br /><small>{STATUS_VI[r.status]}</small>
              </button>
            ))}
          </div><div className="label">Các bản dự toán</div></div>
          <div className="rgroup"><div className="btns">
            <button className="rbtn primary" onClick={newRevisionFrom}><span className="ico">📄</span>Tạo bản mới<br />từ bản này</button>
          </div><div className="label">Phiên bản</div></div>
          <div className="rgroup" style={{ justifyContent: "center", fontSize: 12, color: "#444", maxWidth: 360 }}>
            <div>Trạng thái: <strong>{STATUS_VI[rev.status]}</strong>{rev.approved_at && ` · ${new Date(rev.approved_at).toLocaleString("vi-VN")}`}</div>
            {rev.content_hash && <div title={rev.content_hash}>Hash khóa: <code>{rev.content_hash.slice(0, 16)}…</code></div>}
            {run && <div>Engine {run.engine_version} · Lần tính #{run.id}</div>}
          </div>
        </div>
      )}
      {ribbon === "help" && (
        <div className="ribbon" style={{ fontSize: 12, gap: 24, padding: "8px 16px", alignItems: "center" }}>
          <div><b>Nhập công tác:</b> ở dòng “＋” gõ mã đủ (AF.12111) → Enter. Gõ đầu mã (<code>AE</code>) hoặc từ khóa (<code>Trát,75</code>) → Enter mở <b>Tra mã</b>, tích chọn nhiều mã.<br />
            <b>Diễn giải KL:</b> Alt+D hoặc chuột phải → “Thêm diễn giải”: <code>Móng M1: 1,2*1,8*0,85</code> · dòng kết thúc “:” là ghi chú · hoặc Số CK × Dài × Rộng × Cao.</div>
          <div><b>Mã tạm tính:</b> gõ thẳng đơn giá vào ô ĐG VL/NC/Máy. <b>Giá riêng dự án:</b> sheet Tổng hợp vật tư → sửa Đơn giá (cần lý do).<br />
            <b>Dán từ Excel:</b> copy cột Mã / Tên / Đơn vị / KL → Ctrl+V. <b>Sao chép công tác</b> (kèm diễn giải): Ctrl+C → chọn vị trí → Ctrl+V.</div>
          <div><b>Phím tắt:</b> Insert chèn dòng lên trên · F3 tra mã · F8 xóa dòng · Alt+↑↓ di chuyển · Alt+D diễn giải · F9 tính lại · Ctrl/Shift+click chọn nhiều dòng · chuột phải mở menu</div>
        </div>
      )}

      <div className="fbar">
        <div className="namebox" title="Ô đang chọn">{focus.ref || "—"}</div>
        <div className="fx">fx</div>
        <input value={barText} readOnly={!focus.editable || locked} onChange={(e) => setBarText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void commitBar(); } else if (e.key === "Escape") setBarText(focus.text); }}
          onBlur={() => void commitBar()} aria-label="Thanh công thức"
          placeholder={locked ? "Bản đã phê duyệt — chỉ xem. Vào “Phiên bản & duyệt” → Tạo bản mới để chỉnh sửa." : ""} />
        {focus.hint && <span className="hint">{focus.hint}</span>}
      </div>

      {sheet === "tl" && (
        <TienLuong ref={tl} revision={rev} run={run} releaseId={project.norm_release} locked={locked} showDims={showDims}
          onEdit={onEdit} onFocus={setFocus} onPasteRows={onPasteRows} onContextMenu={(row, x, y) => setCtx({ row, x, y })} />
      )}
      {sheet === "pt" && <PhanTich revision={rev} run={run} />}
      {sheet === "thvt" && <TongHopVatTu run={run} locked={locked} onOverride={(t, price) => setDialog({ kind: "override", t, price, reason: "" })} />}
      {sheet === "thkp" && <TongHopKinhPhi project={project} revision={rev} run={run} sample={sample} />}
      {sheet === "thxd" && <TongHopChiPhiXD project={project} revision={rev} run={run} />}
      {sheet === "tb" && <ChiPhiThietBi revision={rev} locked={locked} onAdd={eqAdd} onSave={eqSave} onDelete={eqDelete} />}
      {sheet === "bia" && <Bia project={project} revision={rev} run={run} total={values ? Number(values.TONG) : null} onEdit={openInfo} />}

      <div className="tabsbar" role="tablist">
        <div className="nav">◂ ▸</div>
        {SHEETS.map(([k, label]) => (
          <button key={k} className={`stab ${sheet === k ? "active" : ""}`} role="tab" aria-selected={sheet === k} onClick={() => { setSheet(k); setFocus({ ref: "", text: "", editable: false }); }}>{label}</button>
        ))}
      </div>
      <div className="statusbar">
        <span>{calcState === "running" ? "⏳ Đang tính…" : calcState === "stale" ? "● Chưa tính lại" : calcState === "error" ? "✖ Lỗi tính toán" : "✔ Sẵn sàng"}</span>
        <span>{lineCount} công tác</span>
        {blocking > 0 && <span className="pill warn" title={run?.warnings.filter((w) => BLOCKING.includes(w.code)).map((w) => w.message).join("\n")}>⚠ {blocking} lỗi dữ liệu</span>}
        {otherWarn > 0 && <span className="pill" title={run?.warnings.filter((w) => !BLOCKING.includes(w.code)).map((w) => w.message).join("\n")}>{otherWarn} cảnh báo</span>}
        {sample && <span className="pill warn">DỮ LIỆU MẪU</span>}
        {locked && <span className="pill">🔒 Đã khóa</span>}
        <span className="grow" />
        {values && (<><span>Trực tiếp: <b>{fmt.money(values.T)}</b></span><span>Trước thuế: <b>{fmt.money(values.GXDTT)}</b></span><span>Sau thuế: <b>{fmt.money(values.GXD)}</b></span></>)}
        {eqTotal > 0 && <span>Thiết bị: <b>{fmt.money(eqTotal)}</b></span>}
      </div>

      {ctx && (
        <div className="ctxmenu" style={{ left: Math.min(ctx.x, window.innerWidth - 300), top: Math.min(ctx.y, window.innerHeight - 420) }} onMouseDown={(e) => e.stopPropagation()} role="menu">
          <button disabled={locked} onClick={run_(actInsert)}>➕ Chèn công tác lên trên<span className="k">Insert</span></button>
          <button disabled={locked} onClick={run_(actTraMa)}>🔎 Tra mã định mức…<span className="k">F3</span></button>
          <button disabled={locked || !ctxLine} onClick={run_(actDetail)}>📐 Thêm diễn giải khối lượng<span className="k">Alt+D</span></button>
          {ctxRow?.kind === "detail" && <button disabled={locked} onClick={run_(() => removeDetail(ctxRow))}>✖ Xóa dòng diễn giải</button>}
          <button disabled={locked || !ctxLine} onClick={run_(() => openProps(ctxLine))}>⚙️ Hệ số Knc/Km, đơn giá tạm tính…</button>
          <hr />
          <button disabled={!ctxLine} onClick={run_(copyLines)}>📋 Sao chép công tác<span className="k">Ctrl+C</span></button>
          <button disabled={locked || !clip.current || !ctxRow?.itemId} onClick={run_(() => { if (ctxRow?.itemId) void pasteClip(ctxRow.itemId, ctxRow.kind === "line" ? ctxRow.line.id : undefined); })}>📌 Dán công tác vào đây{clip.current ? ` (${clip.current.lines.length})` : ""}<span className="k">Ctrl+V</span></button>
          <hr />
          <button disabled={locked || !ctxLine} onClick={run_(() => void moveLine(-1))}>⬆️ Đưa lên<span className="k">Alt+↑</span></button>
          <button disabled={locked || !ctxLine} onClick={run_(() => void moveLine(1))}>⬇️ Đưa xuống<span className="k">Alt+↓</span></button>
          <hr />
          <button disabled={locked || !ctxLine} onClick={run_(deleteSelection)}>🗑️ Xóa dòng công tác<span className="k">F8</span></button>
          <hr />
          <button disabled={locked} onClick={run_(() => setDialog({ kind: "item", mode: "new", name: `Hạng mục ${rev.items.length + 1}` }))}>🗂️ Thêm hạng mục</button>
          <button disabled={locked || !ctxRow?.itemId} onClick={run_(() => { const it = rev.items.find((i) => i.id === ctxRow?.itemId); if (it) setDialog({ kind: "item", mode: "rename", itemId: it.id, name: it.name }); })}>✏️ Đổi tên hạng mục</button>
        </div>
      )}

      {dialog?.kind === "trama" && (
        <TraMa releaseId={project.norm_release} initialQuery={dialog.query} target={`“${itemName(dialog.itemId)}”${dialog.beforeLineId ? " (lên trên dòng đang chọn)" : ""}`}
          onClose={() => setDialog(null)} onPick={(wis) => void insertWorkItems(wis, dialog.itemId, dialog.beforeLineId)}
          onCustom={FULL_CODE.test(dialog.query) || /^[A-Za-z0-9.]{2,12}$/.test(dialog.query) ? (code) => {
            const d = dialog;
            setDialog(null);
            void insertLines(d.itemId, [{ custom_code: code, name: "(Công tác tạm tính — nhập tên)", unit: "đv" }], d.beforeLineId)
              .then(() => toast(`Đã tạo mã tạm tính "${code}". Nhập tên, đơn vị và đơn giá.`)).catch(fail);
          } : undefined} />
      )}
      {dialog?.kind === "props" && (
        <Modal title={`Thuộc tính công tác ${dialog.line.code}`} onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Hủy</button><button className="btn primary" onClick={() => saveProps(dialog)}>Lưu & tính lại</button></>}>
          <p className="doc-sub">{dialog.line.name}</p>
          <div className="row2">
            <div className="field"><label>Hệ số nhân công Knc (làm đêm/lễ…)</label><input value={dialog.k_nc} onChange={(e) => setDialog({ ...dialog, k_nc: e.target.value })} /></div>
            <div className="field"><label>Hệ số máy Km</label><input value={dialog.k_m} onChange={(e) => setDialog({ ...dialog, k_m: e.target.value })} /></div>
          </div>
          <p className="doc-sub" style={{ marginBottom: 6 }}>
            <b>Đơn giá tạm tính</b> (đồng / {dialog.line.unit}). {dialog.line.work_item ? "Công tác có định mức: để trống để tính theo định mức; nhập số sẽ thay đơn giá định mức (có cảnh báo)." : "Mã tạm tính không có định mức — nhập đơn giá để có thành tiền."}
          </p>
          <div className="row2" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
            <div className="field"><label>Vật liệu</label><input value={dialog.manual_vl} onChange={(e) => setDialog({ ...dialog, manual_vl: e.target.value })} /></div>
            <div className="field"><label>Nhân công</label><input value={dialog.manual_nc} onChange={(e) => setDialog({ ...dialog, manual_nc: e.target.value })} /></div>
            <div className="field"><label>Máy</label><input value={dialog.manual_m} onChange={(e) => setDialog({ ...dialog, manual_m: e.target.value })} /></div>
          </div>
          <div className="field"><label>Ghi chú</label><input value={dialog.note} onChange={(e) => setDialog({ ...dialog, note: e.target.value })} /></div>
        </Modal>
      )}
      {dialog?.kind === "info" && (() => {
        const f = dialog.f;
        const set = (k: keyof InfoForm, v: unknown) => setDialog({ kind: "info", f: { ...f, [k]: v } });
        const priceRels = releases.filter((r) => r.kind === "PRICE");
        return (
          <Modal title="Thông tin công trình" onClose={() => setDialog(null)}
            footer={<><button className="btn" onClick={() => setDialog(null)}>Hủy</button><button className="btn primary" onClick={() => saveInfo(f)}>Lưu{locked ? "" : " & tính lại"}</button></>}>
            <div className="field"><label>Tên công trình *</label><input value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
            <div className="row2">
              <div className="field"><label>Mã công trình</label><input value={f.code} onChange={(e) => set("code", e.target.value)} /></div>
              <div className="field"><label>Địa điểm xây dựng</label><input value={f.location} onChange={(e) => set("location", e.target.value)} /></div>
              <div className="field"><label>Chủ đầu tư</label><input value={f.investor} onChange={(e) => set("investor", e.target.value)} /></div>
              <div className="field"><label>Đơn vị lập dự toán</label><input value={f.consultant} onChange={(e) => set("consultant", e.target.value)} /></div>
              <div className="field"><label>Người lập</label><input value={f.preparer} onChange={(e) => set("preparer", e.target.value)} /></div>
              <div className="field"><label>Người kiểm tra / chủ trì</label><input value={f.checker} onChange={(e) => set("checker", e.target.value)} /></div>
            </div>
            {locked && <div className="notice">Bản dự toán đang mở đã khóa: các thay đổi về loại công trình, thuế, bộ giá chỉ áp dụng cho bản dự toán mới.</div>}
            <div className="row2">
              <div className="field"><label>Loại công trình (Bảng 3.3)</label>
                <select value={f.construction_type} onChange={(e) => set("construction_type", e.target.value)}>
                  {CONSTRUCTION_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></div>
              <div className="field"><label>Chi phí XD trước thuế trong TMĐT duyệt (tỷ đồng)</label><input value={f.approved_construction_cost_bn} onChange={(e) => set("approved_construction_cost_bn", e.target.value)} placeholder="để trống → lấy theo kết quả tính" /></div>
              <div className="field"><label>Thuế GTGT (%)</label><input value={f.vat_rate} onChange={(e) => set("vat_rate", e.target.value)} placeholder="để trống → mặc định rule pack" /></div>
              <div className="field"><label>Bộ định mức</label>
                <select value={f.norm_release} onChange={(e) => set("norm_release", Number(e.target.value))}>
                  {releases.filter((r) => r.kind === "NORM").map((r) => <option key={r.id} value={r.id}>{r.name} {r.version}{r.is_sample ? " (MẪU)" : ""}</option>)}
                </select></div>
              <div className="field"><label>Bộ giá nhân công, ca máy</label>
                <select value={f.price_release} onChange={(e) => {
                  const rel = priceRels.find((r) => r.id === Number(e.target.value));
                  setDialog({ kind: "info", f: { ...f, price_release: Number(e.target.value), region: rel?.meta?.regions?.[0] ?? rel?.region ?? f.region, price_period: rel?.meta?.period ?? f.price_period } });
                }}>
                  {priceRels.map((r) => <option key={r.id} value={r.id}>{r.name} {r.version}{r.is_sample ? " (MẪU)" : ""}</option>)}
                </select></div>
              <div className="field"><label>Địa phương / vùng lấy giá</label>
                {(() => { const regs = priceRels.find((r) => r.id === f.price_release)?.meta?.regions; return regs?.length
                  ? <select value={f.region} onChange={(e) => set("region", e.target.value)}>{regs.map((x) => <option key={x}>{x}</option>)}</select>
                  : <input value={f.region} onChange={(e) => set("region", e.target.value)} />; })()}</div>
              <div className="field"><label>Kỳ giá</label><input value={f.price_period} onChange={(e) => set("price_period", e.target.value)} placeholder="2026-Q3" /></div>
            </div>
            <div className="checks">
              <label><input type="checkbox" checked={f.is_remote_area} onChange={(e) => set("is_remote_area", e.target.checked)} /> Vùng núi, biên giới, hải đảo (× 1,1)</label>
              <label><input type="checkbox" checked={f.is_linear} onChange={(e) => set("is_linear", e.target.checked)} /> Công trình theo tuyến</label>
              <label><input type="checkbox" checked={f.is_feasibility_report_only} onChange={(e) => set("is_feasibility_report_only", e.target.checked)} /> Chỉ lập báo cáo KT-KT</label>
            </div>
          </Modal>
        );
      })()}
      {dialog?.kind === "data" && (
        <Modal title="Cập nhật dữ liệu định mức & giá" wide onClose={() => setDialog(null)}
          footer={<button className="btn" onClick={() => setDialog(null)}>Đóng</button>}>
          <DataUpdate onUpdated={() => { void api.get<Page<Release>>("/catalog/releases").then((r) => setReleases(r.results)); }} />
          <p className="doc-sub">Bản dự toán đang mở vẫn dùng bộ dữ liệu cũ. Để dùng bộ mới: ribbon <b>Công trình → Thông tin công trình</b>, chọn bộ định mức / bộ giá mới (nên tạo bản dự toán mới trước).</p>
        </Modal>
      )}
      {dialog?.kind === "item" && (
        <Modal title={dialog.mode === "new" ? "Thêm hạng mục" : "Đổi tên hạng mục"} onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Hủy</button><button className="btn primary" onClick={() => saveItemDialog(dialog)}>Lưu</button></>}>
          <div className="field"><label>Tên hạng mục</label>
            <input autoFocus value={dialog.name} onChange={(e) => setDialog({ ...dialog, name: e.target.value })} onKeyDown={(e) => e.key === "Enter" && saveItemDialog(dialog)} /></div>
        </Modal>
      )}
      {dialog?.kind === "override" && (
        <Modal title={`Giá riêng: ${dialog.t.resource_code} — ${dialog.t.name}`} wide onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Hủy</button><button className="btn primary" onClick={() => saveOverride(dialog)}>Áp dụng & tính lại</button></>}>
          <p className="doc-sub">Giá hiện tại: {dialog.t.price ? Number(dialog.t.price).toLocaleString("vi-VN") : "chưa có"} đ/{dialog.t.unit} ({dialog.t.price_source ?? "—"}). Giá riêng chỉ áp dụng cho bản dự toán này, không sửa bộ giá gốc, và được lưu vết.</p>
          <div className="field"><label>Đơn giá mới (đ/{dialog.t.unit}, chưa VAT, đến hiện trường)</label>
            <input autoFocus inputMode="decimal" value={dialog.price} onChange={(e) => setDialog({ ...dialog, price: e.target.value })} /></div>
          <div className="field"><label>Lý do / nguồn giá *</label>
            <input value={dialog.reason} onChange={(e) => setDialog({ ...dialog, reason: e.target.value })} placeholder="VD: Báo giá NCC ABC ngày 01/11/2026" onKeyDown={(e) => e.key === "Enter" && saveOverride(dialog)} /></div>
          <CatalogPicker initial={dialog.t.name} unit={dialog.t.unit} onPick={(c) => setDialog({ ...dialog, price: fmt.money(c.price), reason: `Công bố giá VLXD Hà Nội ${c.period}: ${c.name}${c.spec ? ` (${c.spec})` : ""} — ${c.context} — tr.${c.page}`.slice(0, 480) })} />
        </Modal>
      )}
      {dialog?.kind === "approve" && (
        <Modal title="Không thể phê duyệt: còn lỗi dữ liệu" onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Quay lại sửa</button><button className="btn primary" disabled={!dialog.reason.trim()} onClick={() => approve(true, dialog.reason)}>Vẫn phê duyệt (ghi lý do)</button></>}>
          <ul>{dialog.warnings.map((w, i) => <li key={i}><code>{w.code}</code> {w.message}</li>)}</ul>
          <div className="field"><label>Lý do phê duyệt dù còn lỗi *</label>
            <input value={dialog.reason} onChange={(e) => setDialog({ ...dialog, reason: e.target.value })} /></div>
        </Modal>
      )}
      {dialog?.kind === "confirm" && (
        <Modal title={dialog.title} onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Hủy</button><button className="btn primary" autoFocus onClick={() => { dialog.onOk(); setDialog(null); }}>Đồng ý</button></>}>
          <p>{dialog.text}</p>
        </Modal>
      )}
    </>
  );
}

/** Áp giá thông báo: tra danh mục công bố giá vật liệu (bản mới nhất) và chọn một dòng. */
function CatalogPicker({ initial, unit, onPick }: { initial: string; unit: string; onPick(c: CatalogItem): void }) {
  const [q, setQ] = useState(initial.split(/[\s,(]/).slice(0, 2).join(" "));
  const [items, setItems] = useState<CatalogItem[] | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => {
      api.get<Page<CatalogItem>>("/catalog/price-items", { query: q, page_size: 100 }).then((r) => setItems(r.results)).catch(() => setItems([]));
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);
  return (
    <div className="field">
      <label>Áp giá thông báo (công bố giá vật liệu Hà Nội mới nhất) — từ khóa cách nhau dấu phẩy</label>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="VD: xi măng,PC40 hoặc cát vàng" />
      <div className="catalog-list">
        <table>
          <thead><tr><th>Tên / quy cách</th><th>ĐV</th><th style={{ textAlign: "right" }}>Giá (chưa VAT)</th><th>Nơi / nhà SX</th></tr></thead>
          <tbody>
            {items?.map((c) => (
              <tr key={c.id} onClick={() => onPick(c)} title={`Trang ${c.page} · ${c.document}`} style={c.unit !== unit.toLowerCase() ? { opacity: 0.6 } : undefined}>
                <td>{c.name}{c.spec ? <span style={{ color: "#616161" }}> · {c.spec}</span> : null}</td><td>{c.unit}</td>
                <td style={{ textAlign: "right" }}>{fmt.money(c.price)}</td><td style={{ color: "#616161" }}>{c.context}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {items && !items.length && <div className="empty" style={{ padding: 8 }}>Không có dòng giá phù hợp (hoặc chưa có dữ liệu công bố giá — bấm “Cập nhật dữ liệu”).</div>}
      </div>
    </div>
  );
}
