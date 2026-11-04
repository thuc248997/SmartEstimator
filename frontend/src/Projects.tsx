import { FormEvent, useEffect, useState } from "react";
import { api, CONSTRUCTION_TYPES, fmt, Page, Project, Release, RulePack } from "./api";
import { errMsg, useToast } from "./ui";
import DataUpdate from "./DataUpdate";

type Tab = "open" | "new" | "data";
const TAB_HASH: Record<Tab, string> = { open: "#/", new: "#/moi", data: "#/du-lieu" };

export default function Projects({ onLogout, initialTab = "open" }: { onLogout: () => void; initialTab?: Tab }) {
  const [tab, setTabState] = useState<Tab>(initialTab);
  const setTab = (t: Tab) => { setTabState(t); window.history.replaceState(null, "", TAB_HASH[t]); };
  const [projects, setProjects] = useState<Project[] | null>(null);
  const toast = useToast();

  const load = () => api.get<Page<Project>>("/projects").then((r) => setProjects(r.results)).catch((e) => {
    if (e.status === 401) onLogout(); else toast(errMsg(e), true);
  });
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="titlebar">
        <div className="logo">SE</div><div className="doc">SmartEstimator — Dự toán xây dựng</div>
        <div className="user"><button className="link" onClick={onLogout}>Đăng xuất</button></div>
      </div>
      <div className="page">
        <div className="backstage">
          <nav>
            <button className={tab === "open" ? "active" : ""} onClick={() => setTab("open")}>📂 Mở công trình</button>
            <button className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>➕ Công trình mới</button>
            <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}>🔄 Dữ liệu định mức & giá</button>
          </nav>
          <main>
            {tab === "open" ? (
              <>
                <h2>Công trình</h2>
                {projects === null ? <p>Đang tải…</p> : projects.length === 0 ? (
                  <p>Chưa có công trình nào. <button className="btn primary" onClick={() => setTab("new")}>Tạo công trình mới</button></p>
                ) : (
                  <table className="plist">
                    <thead><tr><th>Tên công trình</th><th>Loại</th><th>Địa phương / kỳ giá</th><th>TMĐT (tỷ)</th><th>Ngày tạo</th></tr></thead>
                    <tbody>
                      {projects.map((p) => (
                        <tr key={p.id} className="click" onClick={() => (window.location.hash = `#/p/${p.id}`)}>
                          <td><strong>{p.name}</strong>{p.code && <span className="doc-sub"> · {p.code}</span>}</td>
                          <td>{CONSTRUCTION_TYPES.find((c) => c[0] === p.construction_type)?.[1] ?? p.construction_type}</td>
                          <td>{p.region} · {p.price_period}</td>
                          <td>{p.approved_construction_cost_bn == null ? "—" : fmt.qty(p.approved_construction_cost_bn)}</td>
                          <td>{new Date(p.created_at).toLocaleDateString("vi-VN")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : tab === "data" ? (
              <><h2>Dữ liệu định mức & giá</h2><DataUpdate /></>
            ) : (
              <NewProject onCreated={(p) => (window.location.hash = `#/p/${p.id}`)} />
            )}
          </main>
        </div>
      </div>
    </>
  );
}

function NewProject({ onCreated }: { onCreated: (p: Project) => void }) {
  const toast = useToast();
  const [releases, setReleases] = useState<Release[]>([]);
  const [packs, setPacks] = useState<RulePack[]>([]);
  const [f, setF] = useState({
    name: "", code: "", location: "", investor: "", consultant: "", region: "", price_period: "", construction_type: "CIVIL",
    overhead_basis: "DIRECT", labor_overhead_row: "", approved_construction_cost_bn: "",
    is_remote_area: false, is_linear: false, is_feasibility_report_only: false,
    rule_pack: 0, norm_release: 0, price_release: 0, vat_rate: "",
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.get<Page<Release>>("/catalog/releases"), api.get<Page<RulePack>>("/rule-packs")]).then(([r, p]) => {
      setReleases(r.results); setPacks(p.results);
      const norm = r.results.find((x) => x.kind === "NORM"); const price = r.results.find((x) => x.kind === "PRICE");
      setF((s) => ({ ...s, rule_pack: p.results[0]?.id ?? 0, norm_release: norm?.id ?? 0, price_release: price?.id ?? 0,
        region: price?.meta?.regions?.[0] ?? price?.region ?? "", price_period: price?.meta?.period ?? price?.version.split("-sample")[0] ?? "" }));
    }).catch((e) => toast(errMsg(e), true));
  }, [toast]);

  const set = (k: string, v: unknown) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true);
    try {
      const body = { ...f, approved_construction_cost_bn: f.approved_construction_cost_bn || null, vat_rate: f.vat_rate ? String(Number(f.vat_rate) / 100) : null };
      const p = await api.post<Project>("/projects", body);
      await api.post(`/projects/${p.id}/revisions`, { title: "Dự toán lần 1" });
      onCreated(p);
    } catch (e) { toast(errMsg(e), true); } finally { setBusy(false); }
  };
  const sample = releases.some((r) => r.is_sample && (r.id === f.norm_release || r.id === f.price_release));

  return (
    <form onSubmit={submit} style={{ maxWidth: 720 }}>
      <h2>Công trình mới</h2>
      {sample && <div className="notice">Bộ định mức/giá đang chọn là <strong>dữ liệu MẪU</strong>, chỉ dùng để chạy thử.</div>}
      <div className="field"><label>Tên công trình *</label><input required value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="VD: Nhà làm việc 3 tầng" /></div>
      <div className="row2">
        <div className="field"><label>Mã công trình</label><input value={f.code} onChange={(e) => set("code", e.target.value)} /></div>
        <div className="field"><label>Địa điểm xây dựng</label><input value={f.location} onChange={(e) => set("location", e.target.value)} /></div>
        <div className="field"><label>Chủ đầu tư</label><input value={f.investor} onChange={(e) => set("investor", e.target.value)} /></div>
        <div className="field"><label>Đơn vị lập dự toán</label><input value={f.consultant} onChange={(e) => set("consultant", e.target.value)} /></div>
      </div>
      <div className="row2">
        <div className="field"><label>Loại công trình (Bảng 3.3 TT 36/2026)</label>
          <select value={f.construction_type} onChange={(e) => set("construction_type", e.target.value)}>
            {CONSTRUCTION_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></div>
        <div className="field"><label>Chi phí XD trước thuế trong TMĐT duyệt (tỷ đồng)</label>
          <input inputMode="decimal" value={f.approved_construction_cost_bn} onChange={(e) => set("approved_construction_cost_bn", e.target.value)} placeholder="Để trống: tính theo kết quả" /></div>
      </div>
      <div className="row2">
        <div className="field"><label>Cách tính chi phí chung</label>
          <select value={f.overhead_basis} onChange={(e) => set("overhead_basis", e.target.value)}>
            <option value="DIRECT">% trên chi phí trực tiếp (Bảng 3.3)</option>
            <option value="LABOR">% trên chi phí nhân công (Bảng 3.4)</option>
          </select></div>
        {f.overhead_basis === "LABOR" ? (
          <div className="field"><label>Dòng Bảng 3.4</label>
            <select value={f.labor_overhead_row} onChange={(e) => set("labor_overhead_row", e.target.value)} required>
              <option value="">— chọn —</option>
              <option value="EQUIPMENT_INSTALL">Lắp đặt thiết bị / đường dây & TBA / thí nghiệm hiệu chỉnh</option>
              <option value="ROAD_RAIL_MAINTENANCE">Bảo dưỡng đường bộ, đường sắt, báo hiệu hàng hải</option>
              <option value="AGRI_ENV_MANUAL">NN&MT thực hiện hoàn toàn thủ công</option>
            </select></div>
        ) : (
          <div className="field"><label>Thuế GTGT (%) — để trống dùng mặc định rule pack</label>
            <input inputMode="decimal" value={f.vat_rate} onChange={(e) => set("vat_rate", e.target.value)} placeholder="10" /></div>
        )}
      </div>
      <div className="checks">
        <label><input type="checkbox" checked={f.is_remote_area} onChange={(e) => set("is_remote_area", e.target.checked)} /> Vùng núi, biên giới, trên biển, hải đảo (×1,1)</label>
        <label><input type="checkbox" checked={f.is_linear} onChange={(e) => set("is_linear", e.target.checked)} /> Công trình theo tuyến</label>
        <label><input type="checkbox" checked={f.is_feasibility_report_only} onChange={(e) => set("is_feasibility_report_only", e.target.checked)} /> Chỉ lập báo cáo KT-KT</label>
      </div>
      <div className="row2">
        <div className="field"><label>Bộ định mức</label>
          <select value={f.norm_release} onChange={(e) => set("norm_release", Number(e.target.value))}>
            {releases.filter((r) => r.kind === "NORM").map((r) => <option key={r.id} value={r.id}>{r.name} v{r.version}{r.is_sample ? " [MẪU]" : ""}</option>)}
          </select></div>
        <div className="field"><label>Bộ giá</label>
          <select value={f.price_release} onChange={(e) => {
            const rel = releases.find((r) => r.id === Number(e.target.value));
            setF((s) => ({ ...s, price_release: Number(e.target.value), region: rel?.meta?.regions?.[0] ?? rel?.region ?? s.region, price_period: rel?.meta?.period ?? s.price_period }));
          }}>
            {releases.filter((r) => r.kind === "PRICE").map((r) => <option key={r.id} value={r.id}>{r.name} v{r.version}{r.is_sample ? " [MẪU]" : ""}</option>)}
          </select></div>
      </div>
      <div className="row2">
        <div className="field"><label>Địa phương / vùng lấy giá</label>
          {(() => { const regs = releases.find((r) => r.id === f.price_release)?.meta?.regions; return regs?.length
            ? <select value={f.region} onChange={(e) => set("region", e.target.value)}>{regs.map((x) => <option key={x}>{x}</option>)}</select>
            : <input required value={f.region} onChange={(e) => set("region", e.target.value)} />; })()}</div>
        <div className="field"><label>Kỳ giá</label><input required value={f.price_period} onChange={(e) => set("price_period", e.target.value)} placeholder="2026-Q3" /></div>
      </div>
      <div className="field"><label>Quy tắc chi phí (rule pack)</label>
        <select value={f.rule_pack} onChange={(e) => set("rule_pack", Number(e.target.value))}>
          {packs.map((p) => <option key={p.id} value={p.id}>{p.code} v{p.version}{p.is_approved ? "" : " (chưa duyệt)"}</option>)}
        </select></div>
      <button className="btn primary" disabled={busy || !f.name}>{busy ? "Đang tạo…" : "Tạo và mở bảng dự toán"}</button>
    </form>
  );
}
