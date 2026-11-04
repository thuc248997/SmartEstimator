import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, NormComp, Page, WorkGroup, WorkItem } from "./api";
import { Modal } from "./ui";

const KIND: Record<string, string> = { MATERIAL: "Vật liệu", LABOR: "Nhân công", MACHINE: "Máy" };

/** Hộp thoại "Tra mã" kiểu G8: tìm theo đầu mã (AE, AF.12) hoặc nhiều từ khóa tên cách nhau dấu phẩy
 *  (Trát,75), lọc theo chương, xem hao phí, tích chọn nhiều mã rồi chèn một lần. */
export default function TraMa({ releaseId, initialQuery, target, onPick, onCustom, onClose }: {
  releaseId: number;
  initialQuery: string;
  target: string;
  onPick(items: WorkItem[]): void;
  onCustom?(code: string): void;
  onClose(): void;
}) {
  const [q, setQ] = useState(initialQuery);
  const [groups, setGroups] = useState<WorkGroup[]>([]);
  const [chapter, setChapter] = useState("");
  const [items, setItems] = useState<WorkItem[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const [picked, setPicked] = useState<Map<number, WorkItem>>(new Map());
  const [norms, setNorms] = useState<NormComp[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);
  useEffect(() => {
    api.get<WorkGroup[]>("/catalog/work-items/groups", { release: releaseId }).then(setGroups).catch(() => setGroups([]));
  }, [releaseId]);

  const query = useMemo(() => [chapter, q.trim()].filter(Boolean).join(","), [chapter, q]);
  useEffect(() => {
    setLoading(true);
    const t = window.setTimeout(() => {
      api.get<Page<WorkItem>>("/catalog/work-items", { query, release: releaseId, page_size: 300 })
        .then((r) => { setItems(r.results); setCount(r.count); setActive(0); })
        .catch(() => { setItems([]); setCount(0); })
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(t);
  }, [query, releaseId]);

  const cur = items[active];
  useEffect(() => {
    if (!cur) { setNorms(null); return; }
    let live = true;
    const t = window.setTimeout(() => {
      api.get<NormComp[]>(`/catalog/work-items/${cur.id}/norms`).then((n) => live && setNorms(n)).catch(() => live && setNorms(null));
    }, 150);
    return () => { live = false; window.clearTimeout(t); };
  }, [cur]);

  useEffect(() => { listRef.current?.querySelector("tr.active")?.scrollIntoView({ block: "nearest" }); }, [active]);

  const toggle = (w: WorkItem) => setPicked((m) => { const n = new Map(m); if (n.has(w.id)) n.delete(w.id); else n.set(w.id, w); return n; });
  const confirm = () => {
    const list = picked.size ? [...picked.values()] : cur ? [cur] : [];
    if (list.length) onPick(list);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === " " && (e.target as HTMLElement).tagName !== "INPUT" && cur) { e.preventDefault(); toggle(cur); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && cur) { e.preventDefault(); toggle(cur); }
    else if (e.key === "Enter") { e.preventDefault(); confirm(); }
  };

  const exact = items.some((w) => w.code.toLowerCase() === q.trim().toLowerCase());
  return (
    <Modal title={`Tra mã định mức — chèn vào ${target}`} onClose={onClose} wide
      footer={<>
        <span style={{ flex: 1, color: "#616161", fontSize: 12 }}>↑↓ di chuyển · Space / Ctrl+Enter tích chọn · Enter chèn · Esc đóng</span>
        {onCustom && q.trim() && !exact && <button className="btn" onClick={() => onCustom(q.trim())}>Dùng “{q.trim()}” làm mã tạm tính</button>}
        <button className="btn" onClick={onClose}>Hủy</button>
        <button className="btn primary" disabled={!picked.size && !cur} onClick={confirm}>
          {picked.size ? `Chèn ${picked.size} mã đã chọn` : "Chèn mã đang chọn"}
        </button>
      </>}>
      <div className="trama" onKeyDown={onKey}>
        <aside>
          <button className={!chapter ? "on" : ""} onClick={() => setChapter("")}>Tất cả chương</button>
          {groups.map((g) => (
            <button key={g.code} className={chapter === g.code ? "on" : ""} onClick={() => setChapter(g.code)} title={g.name}>
              <b>{g.code}</b> {g.name} <small>({g.count})</small>
            </button>
          ))}
        </aside>
        <section>
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Tìm mã hoặc tên"
            placeholder="Đầu mã (AF.12) hoặc từ khóa tên, nhiều từ cách nhau dấu phẩy: Trát,75" />
          <div className="trama-list" ref={listRef}>
            <table>
              <thead><tr><th style={{ width: 28 }} /><th style={{ width: 96 }}>Mã hiệu</th><th>Tên công tác</th><th style={{ width: 64 }}>Đơn vị</th></tr></thead>
              <tbody>
                {items.map((w, i) => (
                  <tr key={w.id} className={`${i === active ? "active" : ""} ${picked.has(w.id) ? "picked" : ""}`}
                    onClick={() => { setActive(i); inputRef.current?.focus(); }} onDoubleClick={() => onPick([w])}>
                    <td><input type="checkbox" checked={picked.has(w.id)} onChange={() => { toggle(w); inputRef.current?.focus(); }} aria-label={`Chọn ${w.code}`} /></td>
                    <td className="c">{w.code}</td><td>{w.name}</td><td>{w.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!items.length && <div className="empty">{loading ? "Đang tìm…" : "Không tìm thấy công tác phù hợp."}</div>}
          </div>
          <div className="trama-meta">{loading ? "Đang tìm…" : `${count} công tác${count > items.length ? ` (hiện ${items.length} đầu tiên — gõ thêm để lọc)` : ""}`}{picked.size ? ` · đã chọn ${picked.size}` : ""}</div>
          <div className="trama-norms">
            <b>Hao phí định mức {cur ? `${cur.code} (cho 1 ${cur.unit})` : ""}</b>
            {norms && (
              <table>
                <tbody>
                  {norms.map((n) => (
                    <tr key={n.id}><td style={{ width: 70, color: "#616161" }}>{KIND[n.kind] ?? n.kind}</td>
                      <td>{n.is_other_pct ? `${KIND[n.kind]} khác` : `${n.resource_code} — ${n.resource_name}`}</td>
                      <td style={{ width: 60 }}>{n.is_other_pct ? "%" : n.resource_unit}</td>
                      <td className="num" style={{ width: 90 }}>{fmt.qty(n.quantity, 4)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </Modal>
  );
}
