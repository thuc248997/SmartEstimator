import { useState } from "react";
import { CONSTRUCTION_TYPES, fmt, Project, Revision, Run, SummaryRow, vndWords } from "../api";

const BOLD = new Set(["T", "GT", "GXDTT", "GXD"]);

const ITEM_KEYS = new Set(["T", "VL", "NC", "M", "GT", "C", "TT", "TL", "GXDTT", "GTGT", "GXD"]);

/** THKP theo Bảng 3.8 — chọn "Toàn công trình" hoặc từng hạng mục (G8: THKP hạng mục). */
export default function TongHopKinhPhi({ project, revision, run, sample }: { project: Project; revision: Revision; run: Run | null; sample: boolean }) {
  const [scope, setScope] = useState("all");
  if (!run?.result) return <div className="sheet-pad">Chưa có kết quả tính. Bấm <strong>Tính lại (F9)</strong>.</div>;
  const s = run.result.summary;
  const order = new Map(revision.items.map((i) => [String(i.id), i.order * 1e6 + i.id]));
  const items = [...(s.items ?? [])].sort((a, b) => (order.get(a.item_id) ?? 0) - (order.get(b.item_id) ?? 0));
  const item = items.find((i) => i.item_id === scope);
  const rows: SummaryRow[] = item ? s.rows.filter((r) => ITEM_KEYS.has(r.key)).map((r) => ({ ...r, value: item.values[r.key] ?? r.value })) : s.rows;
  const last = rows[rows.length - 1];
  const oh = s.overhead as { table?: string; rate_pct?: string; column?: number; basis_note?: string; remote_coeff?: string };
  return (
    <div className="sheet-pad">
      {items.length > 1 && (
        <div className="seg" role="tablist">
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>Toàn công trình</button>
          {items.map((it) => <button key={it.item_id} className={scope === it.item_id ? "on" : ""} onClick={() => setScope(it.item_id)}>{it.name}</button>)}
        </div>
      )}
      <p className="doc-title">Bảng tổng hợp dự toán chi phí xây dựng{item ? ` — hạng mục ${item.name}` : ""}</p>
      <p className="doc-sub">
        Công trình: <strong>{project.name}</strong> · {CONSTRUCTION_TYPES.find((c) => c[0] === project.construction_type)?.[1]} ·
        Căn cứ: Bảng 3.8 Phụ lục III TT 36/2026/TT-BXD · Rule pack {s.rule_pack.code} v{s.rule_pack.version} · Đơn vị tính: đồng
      </p>
      {sample && <div className="notice">Đang dùng <strong>dữ liệu định mức/giá MẪU</strong> — số liệu chỉ để chạy thử, không dùng cho hồ sơ thật.</div>}
      <table className="xl">
        <thead><tr><th style={{ width: 50 }}>STT</th><th>NỘI DUNG CHI PHÍ</th><th style={{ width: 220 }}>CÁCH TÍNH</th><th style={{ width: 170 }}>GIÁ TRỊ</th><th style={{ width: 90 }}>KÝ HIỆU</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.key === last.key ? "grand" : BOLD.has(r.key) ? "b" : ""}>
              <td style={{ textAlign: "center" }}>{r.stt}</td>
              <td style={{ paddingLeft: r.stt && /^\d+$/.test(r.stt) ? 24 : 8 }}>{r.label}</td>
              <td style={{ fontFamily: "Consolas, monospace", fontSize: 12 }}>{r.formula.replace(/(\d)\.(\d)/g, "$1,$2").replace(/,00%/g, "%")}</td>
              <td className="num">{fmt.money(r.value)}</td>
              <td style={{ textAlign: "center" }}>{r.key}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="words"><b>Bằng chữ ({last.label.toLowerCase()}):</b> {vndWords(last.value)}.</p>
      <p className="doc-sub" style={{ marginTop: 12 }}>
        Chi phí chung: Bảng {oh.table}, tỷ lệ {String(oh.rate_pct).replace(".", ",")}%{oh.remote_coeff && oh.remote_coeff !== "1" ? ` (đã nhân hệ số ${oh.remote_coeff})` : ""}
        {oh.basis_note ? ` — ${oh.basis_note}` : ""} · VAT {Number(s.vat_rate) * 100}% · Engine {run.engine_version} · Hash {run.output_hash.slice(0, 12)}…
      </p>
      {run.warnings.length > 0 && (
        <div className="warnlist">
          <strong>Cảnh báo ({run.warnings.length})</strong>
          <ul>{run.warnings.map((w, i) => <li key={i}><code>{w.code}</code> {w.message}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
