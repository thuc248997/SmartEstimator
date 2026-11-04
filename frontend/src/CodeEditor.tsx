import { useEffect, useRef, useState } from "react";
import type { CustomCellEditorProps } from "ag-grid-react";
import { api, Page, WorkItem } from "./api";

/** Popup cell editor for "Mã hiệu": type a code or words of the name, pick from the norm catalog.
 *  The grid handles Enter/Tab on its popup wrapper before React's delegated handlers run, so the
 *  editor value is kept equal to the code Enter should commit (exact match > highlighted > typed). */
export default function CodeEditor(props: CustomCellEditorProps & { releaseId: number }) {
  const startText = props.eventKey && props.eventKey.length === 1 ? props.eventKey : (props.value as string) ?? "";
  const [text, setText] = useState<string>(startText);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [active, setActive] = useState(0);
  // Như G8: Enter với mã chưa đủ / từ khóa → mở Tra mã; chỉ lấy dòng gợi ý khi người dùng đã chọn bằng ↑↓ hoặc chuột
  const [navigated, setNavigated] = useState(false);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const countRef = useRef(0);
  countRef.current = items.length;
  const navigatedRef = useRef(false);

  useEffect(() => { inputRef.current?.focus(); if (startText.length > 1) inputRef.current?.select(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const q = text.trim();
    if (!q) { setItems([]); return; }
    setLoading(true);
    const t = window.setTimeout(() => {
      api.get<Page<WorkItem>>("/catalog/work-items", { query: q, release: props.releaseId })
        .then((r) => { setItems(r.results.slice(0, 30)); setActive(0); setNavigated(false); })
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 180);
    return () => window.clearTimeout(t);
  }, [text, props.releaseId]);

  navigatedRef.current = navigated;
  const exact = items.find((i) => i.code.toLowerCase() === text.trim().toLowerCase());
  const chosen = exact ? exact.code : navigated && items[active] ? items[active].code : text.trim();
  useEffect(() => { props.onValueChange(chosen); }, [chosen]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    listRef.current?.querySelector("li.active")?.scrollIntoView({ block: "nearest" });
  }, [active]);

  // Native listener on the input runs before the grid's: arrows move the highlight instead of the grid cursor.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); setNavigated(true); setActive((a) => (a === 0 && !navigatedRef.current ? 0 : Math.min(a + 1, countRef.current - 1))); }
      else if (e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); setNavigated(true); setActive((a) => Math.max(a - 1, 0)); }
    };
    el.addEventListener("keydown", onKey);
    return () => el.removeEventListener("keydown", onKey);
  }, []);

  const pick = (code: string) => { props.onValueChange(code); window.setTimeout(() => props.stopEditing(), 0); };

  return (
    <div className="code-editor">
      <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} placeholder="Gõ mã hiệu (AF.12111) hoặc tên công tác…" aria-label="Mã hiệu" />
      <ul ref={listRef} role="listbox">
        {items.map((w, i) => (
          <li key={w.id} className={i === active && navigated ? "active" : ""} role="option" aria-selected={i === active}
            onMouseDown={(e) => { e.preventDefault(); pick(w.code); }} onMouseEnter={() => { setActive(i); setNavigated(true); }}>
            <span className="c">{w.code}</span><span>{w.name}</span><span className="u">{w.unit}</span>
          </li>
        ))}
      </ul>
      {!items.length && <div className="empty">{loading ? "Đang tìm…" : text.trim() ? "Không có trong bộ định mức — Enter để mở Tra mã / tạo mã tạm tính" : "Gõ để tìm trong bộ định mức"}</div>}
      <div className="empty" style={{ borderTop: "1px solid #e1e1e1", fontSize: 11 }}>↑↓ chọn gợi ý · Enter: mã đủ → nhận ngay; mã thiếu / từ khóa (vd <code>Trát,75</code>) → mở <b>Tra mã</b> chọn nhiều</div>
    </div>
  );
}
