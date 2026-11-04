import { useCallback, useEffect, useRef, useState } from "react";
import { api, DataStatus, fmt, UpdateRun } from "./api";
import { errMsg, useToast } from "./ui";

const KIND: Record<string, string> = { NORM: "Định mức", PRICE: "Giá NC + ca máy", CATALOG: "Giá vật liệu", RULE: "Quy tắc" };
const ST: Record<string, [string, string]> = {
  up_to_date: ["✔ Đã là bản mới nhất", "ok"], updated: ["⬆ Đã cập nhật", "up"], error: ["✖ Lỗi", "err"], not_found: ["? Không tìm thấy", "err"],
};

/** Bảng dữ liệu đang dùng + nút "Kiểm tra & cập nhật": tải văn bản mới nhất (TT 38/2026, giá Hà Nội) nếu có. */
export default function DataUpdate({ onUpdated }: { onUpdated?: () => void }) {
  const toast = useToast();
  const [st, setSt] = useState<DataStatus | null>(null);
  const [run, setRun] = useState<UpdateRun | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(() => api.get<DataStatus>("/data-status").then((s) => { setSt(s); if (!run) setRun(s.last_run); }).catch((e) => toast(errMsg(e), true)), [run, toast]);
  useEffect(() => { void load(); return () => window.clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const poll = (id: number) => {
    timer.current = window.setTimeout(async () => {
      try {
        const r = await api.get<UpdateRun>(`/data-updates/${id}`);
        setRun(r);
        if (r.status === "queued" || r.status === "running") return poll(id);
        setBusy(false);
        void load();
        if (r.status === "failed") return toast(`Cập nhật lỗi: ${r.error}`, true);
        const up = r.results.filter((x) => x.status === "updated").length;
        const err = r.results.filter((x) => x.status === "error").length;
        if (err) toast(`Có ${err} nguồn lỗi — xem chi tiết`, true);
        else if (up) { toast(`Đã tải và cập nhật ${up} bộ dữ liệu mới`); onUpdated?.(); }
        else toast("Dữ liệu đã là bản mới nhất");
      } catch (e) { setBusy(false); toast(errMsg(e), true); }
    }, 1500);
  };

  const start = async () => {
    setBusy(true);
    try { const r = await api.post<UpdateRun>("/data-updates", {}); setRun(r); poll(r.id); }
    catch (e) { setBusy(false); toast(errMsg(e), true); }
  };

  const running = busy || run?.status === "queued" || run?.status === "running";
  return (
    <div className="dataupd">
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn primary" onClick={start} disabled={running || !st?.can_update}>
          {running ? "⏳ Đang kiểm tra & tải…" : "🔄 Kiểm tra & cập nhật dữ liệu mới nhất"}
        </button>
        {!st?.can_update && st && <span className="doc-sub" style={{ margin: 0 }}>Chỉ quản trị viên được cập nhật dữ liệu.</span>}
        {run?.finished_at && !running && <span className="doc-sub" style={{ margin: 0 }}>Lần kiểm tra gần nhất: {new Date(run.finished_at).toLocaleString("vi-VN")}</span>}
      </div>
      <p className="doc-sub" style={{ marginTop: 8 }}>
        Nguồn: Thông tư 38/2026/TT-BXD (8 phụ lục định mức) · Sở Xây dựng Hà Nội: đơn giá nhân công, giá ca máy, công bố giá vật liệu
        (dò tự động trên soxaydung.hanoi.gov.vn). Bản mới được nạp thành <b>bộ dữ liệu mới</b>; dự toán cũ giữ nguyên bộ đang dùng.
      </p>

      {run && run.results.length > 0 && (
        <div className="upd-results">
          {run.results.map((r) => (
            <div key={r.source} className={`upd ${ST[r.status]?.[1] ?? ""}`}>
              <div><b>{r.title}</b> <span className="badge">{ST[r.status]?.[0] ?? r.status}</span></div>
              <div>{r.message}</div>
              {(r.documents ?? (r.document ? [r.document] : [])).map((d, i) => (
                <div key={i} className="doc-sub" style={{ margin: 0 }}>📄 {d.number || "—"}{d.issued_on ? ` ngày ${new Date(d.issued_on).toLocaleDateString("vi-VN")}` : ""} · <a href={d.url} target="_blank" rel="noreferrer">tệp nguồn</a>{d.origin === "portal" ? " (cổng Sở XD)" : ""}</div>
              ))}
              {r.warnings?.map((w, i) => <div key={i} className="warnline">⚠ {w}</div>)}
            </div>
          ))}
        </div>
      )}
      {running && run?.log && <pre className="upd-log">{run.log}</pre>}

      <h3 style={{ marginTop: 20 }}>Bộ dữ liệu đang có</h3>
      <table className="plist">
        <thead><tr><th>Loại</th><th>Bộ dữ liệu</th><th>Văn bản nguồn</th><th>Số lượng</th><th>Nạp lúc</th></tr></thead>
        <tbody>
          {st?.releases.map((r) => (
            <tr key={r.id}>
              <td>{KIND[r.kind] ?? r.kind}{r.is_sample && <span className="tag sample" style={{ marginLeft: 6 }}>MẪU</span>}</td>
              <td><b>{r.name}</b><div className="doc-sub" style={{ margin: 0 }}>{r.version}{r.region ? ` · ${r.region}` : ""}</div></td>
              <td>{r.source ? <>{r.source.number}{r.source.issued_on ? ` (${new Date(r.source.issued_on).toLocaleDateString("vi-VN")})` : ""}<div className="doc-sub" style={{ margin: 0 }}>{r.source.issuer}</div></> : "—"}</td>
              <td>{r.counts.work_items ? `${fmt.qty(r.counts.work_items)} mã định mức` : r.counts.prices ? `${fmt.qty(r.counts.prices)} giá` : r.counts.catalog_items ? `${fmt.qty(r.counts.catalog_items)} dòng giá VL` : "—"}
                {typeof r.report.machines_matched === "number" && <div className="doc-sub" style={{ margin: 0 }}>ghép {String(r.report.machines_matched)} máy định mức</div>}</td>
              <td>{new Date(r.created_at).toLocaleString("vi-VN")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
