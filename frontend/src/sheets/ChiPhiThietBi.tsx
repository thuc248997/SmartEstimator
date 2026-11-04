import { useEffect, useRef, useState } from "react";
import { Equipment, fmt, Revision, vndWords } from "../api";
import { sumEquipment } from "./TongHopChiPhiXD";

type Field = "name" | "unit" | "quantity" | "unit_price" | "vat_rate" | "note";
const parse = (f: Field, v: string): string => {
  if (f === "name" || f === "unit" || f === "note") return v.trim();
  let s = v.trim().replace(/\s/g, "").replace(/%$/, "");
  if (f === "unit_price") s = s.replace(/\./g, "").replace(",", ".");
  else s = s.replace(",", ".");
  if (f === "vat_rate") return String(Number(s) / 100);
  return s;
};
const show = (e: Equipment, f: Field) =>
  f === "unit_price" ? fmt.money(e.unit_price) : f === "quantity" ? fmt.qty(e.quantity) : f === "vat_rate" ? `${fmt.qty(Number(e.vat_rate) * 100, 2)}` : e[f];

/** TH chi phí thiết bị (G8: "TH Chi Phí TB"): nhập thiết bị với giá trước thuế, thuế suất; tách khỏi chi phí xây dựng. */
export default function ChiPhiThietBi({ revision, locked, onSave, onAdd, onDelete }: {
  revision: Revision; locked: boolean;
  onSave(e: Equipment, body: Partial<Record<Field, string>>): void;
  onAdd(name: string): void;
  onDelete(e: Equipment): void;
}) {
  const [draft, setDraft] = useState("");
  const list = [...(revision.equipment ?? [])].sort((a, b) => a.order - b.order || a.id - b.id);
  const t = sumEquipment(list);
  const cell = (e: Equipment, f: Field, num = false) => locked ? <td className={num ? "num" : ""}>{show(e, f)}</td> : (
    <td className={num ? "num" : ""} style={{ padding: 0 }}>
      <EqInput value={show(e, f)} num={num} label={f} onCommit={(v) => onSave(e, { [f]: parse(f, v) })} />
    </td>
  );
  return (
    <div className="sheet-pad">
      <p className="doc-title">Bảng tổng hợp chi phí thiết bị</p>
      <p className="doc-sub">Nhập thiết bị mua sắm (giá trước thuế GTGT, đã gồm vận chuyển, lắp đặt nếu có). Đơn vị tính: đồng. Thuế suất nhập theo % (vd 10).</p>
      <table className="xl">
        <thead><tr><th style={{ width: 44 }}>STT</th><th>TÊN THIẾT BỊ</th><th style={{ width: 70 }}>ĐƠN VỊ</th><th style={{ width: 90 }}>SỐ LƯỢNG</th>
          <th style={{ width: 130 }}>ĐƠN GIÁ TRƯỚC THUẾ</th><th style={{ width: 140 }}>THÀNH TIỀN TRƯỚC THUẾ</th><th style={{ width: 70 }}>THUẾ (%)</th>
          <th style={{ width: 120 }}>THUẾ GTGT</th><th style={{ width: 140 }}>SAU THUẾ</th><th style={{ width: 180 }}>GHI CHÚ</th>{!locked && <th style={{ width: 36 }} />}</tr></thead>
        <tbody>
          {list.map((e, i) => (
            <tr key={e.id}>
              <td style={{ textAlign: "center" }}>{i + 1}</td>{cell(e, "name")}{cell(e, "unit")}{cell(e, "quantity", true)}{cell(e, "unit_price", true)}
              <td className="num">{fmt.money(e.amount)}</td>{cell(e, "vat_rate", true)}<td className="num">{fmt.money(e.vat)}</td>
              <td className="num"><b>{fmt.money(e.amount_after_tax)}</b></td>{cell(e, "note")}
              {!locked && <td><button className="linkbtn" title="Xóa thiết bị" onClick={() => onDelete(e)}>✕</button></td>}
            </tr>
          ))}
          {!locked && (
            <tr>
              <td style={{ textAlign: "center", color: "#a3a3a3" }}>＋</td>
              <td colSpan={9} style={{ padding: 0 }}>
                <input className="cellin" placeholder="Gõ tên thiết bị mới rồi Enter (vd Điều hòa 18000BTU)…" value={draft}
                  onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) { onAdd(draft.trim()); setDraft(""); } }} />
              </td><td />
            </tr>
          )}
          <tr className="grand"><td /><td>TỔNG CỘNG</td><td /><td /><td /><td className="num">{fmt.money(t.before)}</td><td /><td className="num">{fmt.money(t.vat)}</td>
            <td className="num">{fmt.money(t.after)}</td><td />{!locked && <td />}</tr>
        </tbody>
      </table>
      {list.length > 0 && <p className="words"><b>Bằng chữ:</b> {vndWords(t.after)}.</p>}
    </div>
  );
}

/** Ô nhập giữ bản nháp riêng khi đang gõ, nên dữ liệu tải lại giữa chừng không làm mất giá trị đang nhập. */
function EqInput({ value, num, label, onCommit }: { value: string; num: boolean; label: string; onCommit(v: string): void }) {
  const [text, setText] = useState(value);
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setText(value); }, [value]);
  return (
    <input className={`cellin ${num ? "num" : ""}`} value={text} aria-label={label}
      onFocus={() => { editing.current = true; }}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); else if (e.key === "Escape") { setText(value); editing.current = false; } }}
      onBlur={() => { editing.current = false; if (text !== value) onCommit(text); }} />
  );
}
