import { useMemo, useRef, useState } from "react";
import { api, BoqCandidate, BoqCommitResult, BoqField, BoqLine, BoqPreview, fmt, WorkItem } from "./api";
import TraMa from "./TraMa";
import { errMsg, Modal } from "./ui";

/** Quy đổi đơn vị phía giao diện (bản rút gọn của backend/apps/boqimport/units.py) — chỉ để hiển thị KL
 *  khi người dùng tự tra mã khác; khi ghi, máy chủ tính lại hệ số. */
const BASES: [string, string, number][] = [
  ["cau kien", "cau kien", 1], ["moi noi", "moi noi", 1], ["chi tieu", "chi tieu", 1],
  ["m3", "m3", 1], ["m2", "m2", 1], ["md", "m", 1], ["km", "m", 1000], ["m", "m", 1],
  ["tan", "tan", 1], ["kg", "tan", 0.001], ["t", "tan", 1], ["ha", "ha", 1], ["thiet bi", "cai", 1], ["cai", "cai", 1],
  ["chiec", "cai", 1], ["bo", "cai", 1], ["tu", "cai", 1], ["con", "cai", 1], ["may", "cai", 1], ["module", "cai", 1],
  ["cum", "cai", 1], ["dau", "cai", 1], ["cong", "cong", 1], ["ca", "ca", 1], ["lit", "lit", 1], ["coc", "coc", 1], ["diem", "diem", 1],
  ["hop", "cai", 1], ["cuon", "cuon", 1], ["tam", "tam", 1], ["vien", "vien", 1], ["tru", "tru", 1], ["kw", "kw", 1],
];
function parseUnit(raw: string): [number, string] {
  const s = raw.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D")
    .replace(/³/g, "3").replace(/²/g, "2").toLowerCase().replace("/1km", "").trim();
  const m = /^(\d+(?:[.,]\d+)?)?\s*(.*)$/.exec(s);
  const num = m?.[1] ? Number(m[1].replace(",", ".")) : 1;
  const rest = (m?.[2] ?? s).replace(/[()]/g, " ").replace(/\s+/g, " ").trim();
  for (const [k, base, f] of BASES) if (rest === k || rest.startsWith(k + " ") || rest.startsWith(k + "/")) return [num * f, base];
  return [num, rest];
}
function unitFactor(boq: string, norm: string): number | null {
  const [fa, a] = parseUnit(boq), [fb, b] = parseUnit(norm);
  return a && b && a === b ? fa / fb : null;
}

type Kind = "work" | "equipment";
type Choice = { include: boolean; pick: BoqCandidate | null; factor: string; kind: Kind; price: string };
const key = (ii: number, li: number) => `${ii}:${li}`;
const FIELD_LABEL: Record<BoqField, string> = { name: "Tên công tác", unit: "Đơn vị", qty: "Khối lượng", code: "Mã hiệu (nếu có)", stt: "STT", item: "Cột hạng mục (nếu có)" };

function initChoices(p: BoqPreview): Record<string, Choice> {
  const out: Record<string, Choice> = {};
  p.items.forEach((it, ii) => it.lines.forEach((l, li) => { out[key(ii, li)] = { include: true, pick: l.selected, factor: "", kind: l.kind === "equipment" ? "equipment" : "work", price: "" }; }));
  return out;
}

function status(l: BoqLine, c: Choice): { cls: string; text: string; title: string } {
  if (c.kind === "equipment") {
    const base = "Thiết bị → sheet Chi phí thiết bị (giá theo báo giá)";
    if (!c.pick) return { cls: "st-eq", text: "Thiết bị", title: `${base}; không tính công lắp đặt (TT 38 không có định mức phù hợp, hoặc bạn bỏ chọn)` };
    if (c.pick.work_item !== l.selected?.work_item || l.source !== "match" || l.confidence === "high")
      return { cls: "st-eq", text: "TB + lắp đặt", title: `${base} + dòng công lắp đặt theo mã đã chọn` };
    return { cls: "st-warn", text: "TB + lắp: xem", title: `${base}. Mã lắp đặt là gợi ý gần nhất — kiểm tra lại` };
  }
  if (l.kind === "lump" && !c.pick) return { cls: "st-none", text: "Trọn gói", title: "Khoản trọn gói: nhập thành dòng tạm tính, cần nhập đơn giá" };
  if (!c.pick) return { cls: "st-none", text: "Tạm tính", title: "Không gắn mã định mức: nhập dưới dạng mã tạm tính TT.xx, cần nhập đơn giá tay" };
  if (c.pick.work_item !== l.selected?.work_item) return { cls: "st-ok", text: "Đã chọn", title: "Bạn đã chọn mã này" };
  if (l.source === "code") return { cls: "st-ok", text: "Mã trong file", title: "Mã hiệu có sẵn trong file BoQ" };
  if (l.source === "memory") return { cls: "st-ok", text: "Đã nhớ", title: "Lần nhập trước bạn đã chọn mã này cho cùng tên công tác" };
  if (l.confidence === "high") return { cls: "st-ok", text: "Khớp tốt", title: "Tên và đơn vị khớp rõ ràng" };
  return { cls: "st-warn", text: "Cần xem", title: "Có nhiều mã gần giống (khác khoảng kích thước, chương…) — kiểm tra lại" };
}

export default function BoqImport({ revisionId, releaseId, onClose, onDone }: {
  revisionId: number; releaseId: number; onClose(): void; onDone(r: BoqCommitResult): void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BoqPreview | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [itemNames, setItemNames] = useState<string[]>([]);
  const [busy, setBusy] = useState<"" | "read" | "save">("");
  const [error, setError] = useState("");
  const [onlyReview, setOnlyReview] = useState(false);
  const [layout, setLayout] = useState<{ sheet: string; header_row: string; columns: Record<BoqField, string> } | null>(null);
  const [trama, setTrama] = useState<{ ii: number; li: number; query: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const read = async (f: File, manual?: typeof layout) => {
    setBusy("read"); setError("");
    const form = new FormData();
    form.append("file", f);
    if (manual) {
      form.append("sheet", manual.sheet);
      form.append("header_row", manual.header_row);
      form.append("columns", JSON.stringify(Object.fromEntries(Object.entries(manual.columns).map(([k, v]) => [k, v ? Number(v) : null]))));
    }
    try {
      const p = await api.upload<BoqPreview>(`/revisions/${revisionId}/boq-import/preview`, form);
      setPreview(p);
      setChoices(initChoices(p));
      setItemNames(p.items.map((i) => i.name));
      setLayout({ sheet: p.sheet, header_row: String(p.header_row), columns: Object.fromEntries(Object.entries(p.columns).map(([k, v]) => [k, v ? String(v) : ""])) as Record<BoqField, string> });
    } catch (e) { setError(errMsg(e)); }
    finally { setBusy(""); }
  };

  const set = (k: string, patch: Partial<Choice>) => setChoices((c) => ({ ...c, [k]: { ...c[k], ...patch } }));

  const counts = useMemo(() => {
    let incl = 0, coded = 0, custom = 0, review = 0, badUnit = 0, equip = 0, install = 0;
    preview?.items.forEach((it, ii) => it.lines.forEach((l, li) => {
      const c = choices[key(ii, li)];
      if (!c?.include) return;
      incl++;
      if (c.kind === "equipment") { equip++; if (c.pick) install++; if (status(l, c).cls === "st-warn") review++; return; }
      if (c.pick) { coded++; if (c.pick.factor === null && !(Number(c.factor) > 0)) badUnit++; } else custom++;
      if (status(l, c).cls === "st-warn") review++;
    }));
    return { incl, coded, custom, review, badUnit, equip, install };
  }, [preview, choices]);

  const commit = async () => {
    if (!preview) return;
    setBusy("save"); setError("");
    const items = preview.items.map((it, ii) => ({
      name: itemNames[ii] || it.name,
      lines: it.lines.flatMap((l, li) => {
        const c = choices[key(ii, li)];
        if (!c?.include) return [];
        return [{ row: l.row, name: l.name, unit: l.unit, quantity: l.quantity, details: l.details, work_item: c.pick?.work_item ?? null, factor: c.factor || null, kind: c.kind, unit_price: c.kind === "equipment" && c.price ? c.price.replace(/[.\s]/g, "").replace(",", ".") : null }];
      }),
    })).filter((it) => it.lines.length);
    try {
      const r = await api.post<BoqCommitResult>(`/revisions/${revisionId}/boq-import/commit`, { filename: preview.filename, items, calculate: true });
      onDone(r);
    } catch (e) { setError(errMsg(e)); setBusy(""); }
  };

  const pickFromTraMa = (wis: WorkItem[]) => {
    if (!trama || !preview || !wis.length) return;
    const w = wis[0];
    const l = preview.items[trama.ii].lines[trama.li];
    const f = unitFactor(l.unit, w.unit);
    set(key(trama.ii, trama.li), { pick: { work_item: w.id, code: w.code, name: w.name, unit: w.unit, score: 0, factor: f === null ? null : String(f), reasons: [], group: "", ref: "" } });
    setTrama(null);
  };

  // ---------------------------------------------------------------- bước 1: chọn file
  if (!preview) {
    return (
      <Modal title="Nhập BoQ từ Excel" onClose={onClose}
        footer={<><button className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary" disabled={!file || busy !== ""} onClick={() => file && void read(file)}>{busy ? "Đang đọc file…" : "Đọc file & gợi ý mã"}</button></>}>
        <div className="boq-pick">
          <p>Tải lên bảng khối lượng bóc từ bản vẽ (file Excel <b>.xlsx</b> bất kỳ của đơn vị thiết kế). Chỉ cần có cột <b>tên công tác</b>, <b>đơn vị</b> và <b>khối lượng</b>; không cần mã định mức.</p>
          <ul>
            <li>Hệ thống tự nhận dòng tiêu đề, các cột, tiêu đề hạng mục (A, B, I, II… hoặc dòng không có đơn vị) và dòng diễn giải khối lượng.</li>
            <li>Mỗi dòng được gợi ý mã định mức TT 38/2026 theo tên + đơn vị + kích thước (dày, cao, đường kính…); khối lượng được quy đổi sang đơn vị định mức (vd 45 m3 → 0,45 × 100m3).</li>
            <li>Dòng chỉ ghi tên thiết bị (loa, camera, switch, tủ rack… đơn vị cái / bộ) được tách sang <b>Chi phí thiết bị</b> (nhập đơn giá theo báo giá) kèm một dòng <b>công lắp đặt</b> theo định mức nếu có mã phù hợp.</li>
            <li>Giá vật liệu chưa có trong bộ giá được <b>tự áp từ công bố giá</b> địa phương khi tên và đơn vị khớp rõ (có ghi nguồn).</li>
            <li>Bạn xem lại các dòng “Cần xem”, rồi bấm nhập: dự toán được tính ngay.</li>
          </ul>
          <input ref={inputRef} type="file" accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Chọn file BoQ" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); setError(""); if (f) void read(f); }} />
          {busy === "read" && <div className="boq-note">Đang đọc file và tìm mã phù hợp…</div>}
          {error && <div className="boq-error" role="alert">{error}</div>}
        </div>
      </Modal>
    );
  }

  // ---------------------------------------------------------------- bước 2: duyệt
  const headerOpts = preview.headers;
  return (
    <>
      <Modal title={`Nhập BoQ — ${preview.filename}`} onClose={onClose} wide
        footer={<>
          <span className="boq-sum">
            Nhập <b>{counts.incl}</b> dòng: {counts.coded} công tác có mã, {counts.custom} tạm tính, {counts.equip} thiết bị ({counts.install} kèm công lắp đặt)
            {counts.review > 0 && <> · <span className="st-warn-t">{counts.review} dòng nên xem lại</span></>}
            {counts.badUnit > 0 && <> · <span className="st-err-t">{counts.badUnit} dòng thiếu hệ số quy đổi</span></>}
          </span>
          <button className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary" disabled={busy !== "" || !counts.incl || counts.badUnit > 0} onClick={() => void commit()}>
            {busy === "save" ? "Đang nhập & tính…" : `Nhập ${counts.incl} dòng & tính dự toán`}
          </button>
        </>}>
        <div className="boq-review">
          {layout && (
            <details className="boq-layout">
              <summary>Cách đọc file: sheet <b>{preview.sheet}</b>, tiêu đề ở dòng <b>{preview.header_row}</b>,
                {" "}{(Object.keys(FIELD_LABEL) as BoqField[]).filter((f) => preview.columns[f]).map((f) => `${FIELD_LABEL[f]} = cột ${preview.headers.find((h) => h.col === preview.columns[f])?.letter ?? preview.columns[f]}`).join(", ")}
                {" "}— <u>sửa nếu đọc sai</u></summary>
              <div className="boq-layout-form">
                <label>Sheet<select value={layout.sheet} onChange={(e) => setLayout({ ...layout, sheet: e.target.value })}>{preview.sheets.map((s) => <option key={s}>{s}</option>)}</select></label>
                <label>Dòng tiêu đề<input type="number" min={1} value={layout.header_row} onChange={(e) => setLayout({ ...layout, header_row: e.target.value })} /></label>
                {(Object.keys(FIELD_LABEL) as BoqField[]).map((f) => (
                  <label key={f}>{FIELD_LABEL[f]}
                    <select value={layout.columns[f]} onChange={(e) => setLayout({ ...layout, columns: { ...layout.columns, [f]: e.target.value } })}>
                      <option value="">— không có —</option>
                      {headerOpts.map((h) => <option key={h.col} value={h.col}>{h.letter}{h.text ? `: ${h.text.slice(0, 30)}` : ""}</option>)}
                    </select>
                  </label>
                ))}
                <button className="btn" disabled={busy !== ""} onClick={() => file && void read(file, layout)}>Đọc lại</button>
              </div>
            </details>
          )}
          {(preview.warnings.length > 0 || preview.skipped.length > 0) && (
            <div className="boq-note">
              {preview.warnings.join(" ")}
              {preview.skipped.length > 0 && ` Bỏ qua ${preview.skipped.length} dòng (${[...new Set(preview.skipped.map((s) => s.reason.toLowerCase()))].join(", ")}).`}
            </div>
          )}
          <div className="boq-toolbar">
            <label><input type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} /> Chỉ hiện dòng cần xem / tạm tính</label>
            <span className="boq-legend"><span className="st st-ok">Khớp tốt</span> tự chọn <span className="st st-warn">Cần xem</span> đã chọn mã gần nhất, nên kiểm tra <span className="st st-none">Tạm tính</span> chưa có mã phù hợp <span className="st st-eq">Thiết bị</span> vào Chi phí thiết bị</span>
          </div>
          {error && <div className="boq-error" role="alert">{error}</div>}
          <table className="boq-table">
            <thead>
              <tr>
                <th style={{ width: 26 }} /><th style={{ width: 40 }}>STT</th><th>Công tác theo BoQ</th><th style={{ width: 52 }}>ĐV</th>
                <th style={{ width: 80 }} className="num">KL BoQ</th><th style={{ width: 110 }}>Loại / trạng thái</th><th style={{ width: 380 }}>Mã định mức (thiết bị: mã công lắp đặt)</th>
                <th style={{ width: 96 }} className="num">KL định mức</th>
              </tr>
            </thead>
            <tbody>
              {preview.items.map((it, ii) => {
                const rows = it.lines.map((l, li) => ({ l, li, c: choices[key(ii, li)] })).filter(({ l, c }) => !onlyReview || status(l, c).cls !== "st-ok");
                if (!rows.length) return null;
                return [
                  <tr key={`h${ii}`} className="boq-item">
                    <td colSpan={8}>
                      <input aria-label="Tên hạng mục" value={itemNames[ii] ?? ""} onChange={(e) => setItemNames((n) => n.map((x, j) => (j === ii ? e.target.value : x)))} />
                      <small> {it.lines.length} công tác</small>
                    </td>
                  </tr>,
                  ...rows.map(({ l, li, c }) => {
                    const st = status(l, c);
                    const f = c.pick ? (c.pick.factor !== null ? Number(c.pick.factor) : Number(c.factor) || null) : 1;
                    const q = l.quantity === null ? null : Number(l.quantity);
                    const conv = q !== null && f ? q * f : null;
                    return (
                      <tr key={`${ii}-${li}`} className={c.include ? "" : "off"}>
                        <td><input type="checkbox" checked={c.include} aria-label={`Nhập dòng ${l.row}`} onChange={(e) => set(key(ii, li), { include: e.target.checked })} /></td>
                        <td>{l.stt}</td>
                        <td>
                          <div>{l.name}</div>
                          {l.details.length > 0 && <small className="muted">Diễn giải: {l.details.length} dòng</small>}
                          {l.warnings.map((w) => <div key={w} className="boq-w">⚠ {w}</div>)}
                        </td>
                        <td>{l.unit}</td>
                        <td className="num">{fmt.qty(l.quantity)}</td>
                        <td>
                          <select className="boq-kind" value={c.kind} aria-label={`Loại dòng ${l.row}`} onChange={(e) => set(key(ii, li), { kind: e.target.value as Kind })}>
                            <option value="work">Công tác</option>
                            <option value="equipment">Thiết bị</option>
                          </select>
                          <span className={`st ${st.cls}`} title={st.title}>{st.text}</span>
                          {c.kind === "equipment" && (
                            <input className="boq-price" inputMode="numeric" placeholder="Đơn giá TB (đ)" value={c.price} aria-label={`Đơn giá thiết bị dòng ${l.row}`}
                              onChange={(e) => set(key(ii, li), { price: e.target.value })} title="Đơn giá trước thuế theo báo giá; để trống thì nhập sau ở sheet Chi phí thiết bị" />
                          )}
                        </td>
                        <td>
                          <select className="boq-pickcode" value={c.pick ? String(c.pick.work_item) : ""} aria-label={`Mã định mức cho dòng ${l.row}`}
                            onChange={(e) => {
                              const v = e.target.value;
                              if (v === "__trama") { setTrama({ ii, li, query: "" }); return; }
                              const cand = [...l.candidates, ...(c.pick ? [c.pick] : [])].find((x) => String(x.work_item) === v) ?? null;
                              set(key(ii, li), { pick: cand, factor: "" });
                            }}>
                            {c.pick && !l.candidates.some((x) => x.work_item === c.pick!.work_item) && <option value={c.pick.work_item}>{c.pick.code} — {c.pick.name.slice(0, 70)} ({c.pick.unit})</option>}
                            {l.candidates.map((x) => <option key={x.work_item} value={x.work_item}>{x.code} — {x.name.slice(0, 70)} ({x.unit}){x.factor === null ? " ⚠ khác đơn vị" : ""}</option>)}
                            <option value="">{c.kind === "equipment" ? "— Không tính công lắp đặt —" : "— Không dùng mã (tạm tính, nhập giá tay) —"}</option>
                            <option value="__trama">🔎 Tra mã khác…</option>
                          </select>
                          {c.pick && (c.pick.group || c.pick.ref || c.pick.reasons.length > 0) && (
                            <small className="muted">{[c.pick.group, c.pick.ref, ...c.pick.reasons].filter(Boolean).join(" · ")}</small>
                          )}
                          {c.pick && c.pick.factor === null && (
                            <div className="boq-factor">1 {l.unit} = <input value={c.factor} placeholder="?" onChange={(e) => set(key(ii, li), { factor: e.target.value.replace(",", ".") })} aria-label="Hệ số quy đổi" /> {c.pick.unit}</div>
                          )}
                        </td>
                        <td className="num">{conv === null ? "" : fmt.qty(conv, 4)}<br /><small className="muted">{c.pick ? c.pick.unit : l.unit}</small></td>
                      </tr>
                    );
                  }),
                ];
              })}
            </tbody>
          </table>
        </div>
      </Modal>
      {trama && (
        <TraMa releaseId={releaseId} initialQuery={trama.query} target={`dòng BoQ “${preview.items[trama.ii].lines[trama.li].name.slice(0, 60)}”`}
          onClose={() => setTrama(null)} onPick={pickFromTraMa} />
      )}
    </>
  );
}
