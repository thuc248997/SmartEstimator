// Thin fetch wrapper over the Django REST API (/api/v1). Token stored per browser.
const TOKEN_KEY = "se.token";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(typeof data === "object" && data && "detail" in data ? String((data as { detail: unknown }).detail) : `HTTP ${status}`);
  }
}

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

async function request<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof URLSearchParams) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(url, { method, headers, body: payload });
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  get: <T>(p: string, q?: Record<string, string | number | undefined>) => request<T>("GET", p, undefined, q),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b),
  patch: <T>(p: string, b?: unknown) => request<T>("PATCH", p, b),
  del: (p: string) => request<void>("DELETE", p),
  async login(username: string, password: string) {
    const r = await request<{ token: string }>("POST", "/auth/token", new URLSearchParams({ username, password }));
    setToken(r.token);
  },
  async download(path: string): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch(`/api/v1${path}`, { method: "POST", headers: { Authorization: `Token ${getToken()}` } });
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({})));
    const cd = res.headers.get("content-disposition") || "";
    const m = /filename="([^"]+)"/.exec(cd);
    return { blob: await res.blob(), filename: m ? m[1] : "du-toan.xlsx" };
  },
};

// ---------------------------------------------------------------- types
export interface Page<T> { count: number; results: T[] }
export interface Release {
  id: number; kind: "NORM" | "PRICE" | "RULE" | "CATALOG"; name: string; version: string; region: string; is_sample: boolean;
  meta?: { regions?: string[]; period?: string; documents?: { number?: string; url?: string }[] };
}
export interface UpdateResult {
  source: string; title: string; status: "up_to_date" | "updated" | "error" | "not_found"; message: string; release_id?: number;
  warnings?: string[]; document?: { number: string; issued_on: string; url: string; origin: string };
  documents?: { number: string; issued_on: string; url: string; origin: string }[];
}
export interface UpdateRun { id: number; status: "queued" | "running" | "done" | "failed"; results: UpdateResult[]; log: string; error: string; started_at: string; finished_at: string | null }
export interface DataStatus {
  can_update: boolean; last_run: UpdateRun | null;
  releases: {
    id: number; kind: string; name: string; version: string; region: string; is_sample: boolean; effective_from: string | null; created_at: string;
    source: { number: string; issuer: string; url: string; issued_on: string | null } | null;
    counts: { work_items: number; prices: number; catalog_items: number }; meta: Record<string, unknown>; report: Record<string, unknown>;
  }[];
}
export interface CatalogItem { id: number; release: number; period: string; name: string; spec: string; unit: string; price: string; context: string; page: number; document: string }
export interface RulePack { id: number; code: string; version: string; title: string; is_approved: boolean }
export interface Project {
  id: number; name: string; code: string; location: string; region: string; price_period: string;
  construction_type: string; overhead_basis: "DIRECT" | "LABOR"; labor_overhead_row: string;
  is_remote_area: boolean; is_linear: boolean; is_feasibility_report_only: boolean;
  approved_construction_cost_bn: string | null; vat_rate: string | null;
  rule_pack: number; norm_release: number; price_release: number; created_at: string;
  investor: string; consultant: string; preparer: string; checker: string;
}
export interface Line {
  id: number; item: number; order: number; work_item: number | null; custom_code: string; code: string;
  name: string; unit: string; quantity_expr: string; quantity: string; k_nc: string; k_m: string; note: string; version: number;
  details: Detail[]; manual_vl: string | null; manual_nc: string | null; manual_m: string | null;
}
/** Một dòng diễn giải khối lượng: ghi chú, công thức, hoặc Số CK × Dài × Rộng × Cao. */
export interface Detail { text: string; expr: string; n: string | null; l: string | null; w: string | null; h: string | null; value?: string | null }
export interface Equipment {
  id: number; revision: number; order: number; name: string; unit: string; quantity: string; unit_price: string;
  vat_rate: string; note: string; amount: string; vat: string; amount_after_tax: string;
}
export interface ItemSummary { item_id: string; name: string; lines: number; values: Record<string, string> }
export interface WorkGroup { code: string; name: string; count: number }
export interface NormComp { id: number; kind: string; resource_code: string | null; resource_name: string | null; resource_unit: string | null; quantity: string; is_other_pct: boolean }
export interface Item { id: number; revision: number; order: number; name: string; lines: Line[] }
export interface Override { id: number; resource: number; resource_code: string; price: string; reason: string }
export interface Revision {
  id: number; project: number; number: number; title: string; status: "draft" | "review" | "approved" | "issued";
  is_locked: boolean; content_hash: string; approved_at: string | null; items: Item[]; overrides: Override[];
  equipment: Equipment[];
}
export interface WorkItem { id: number; code: string; name: string; unit: string; group_code: string; is_sample: boolean }
export interface Warning { code: string; message: string; line_id?: string; resource_code?: string }
export interface Component {
  resource_code?: string | null; kind: string; name?: string | null; unit?: string | null; norm_qty?: string;
  consumption?: string; price?: string | null; price_source?: string | null; amount_per_unit?: string | null; other_pct?: string;
}
export interface CalcLine {
  line: number; item: number; code: string; name: string; unit: string; quantity: string;
  unit_vl: string; unit_nc: string; unit_m: string; vl: string; nc: string; m: string; direct: string;
  warnings: Warning[]; breakdown: { components: Component[]; quantity: { expr: string; value: string } };
}
export interface SummaryRow { stt: string; key: string; label: string; formula: string; value: string; rate_pct?: string }
export interface ResourceTotal {
  resource_code: string; kind: string; name: string; unit: string; quantity: string;
  price: string | null; price_source: string | null; amount: string | null;
}
export interface Run {
  id: number; revision: number; status: string; engine_version: string; input_hash: string; output_hash: string;
  warnings: Warning[]; error: string; created_at: string; finished_at: string | null;
  result: null | { summary: { rows: SummaryRow[]; values: Record<string, string>; items?: ItemSummary[]; overhead: Record<string, unknown>; vat_rate: string; rule_pack: { code: string; version: string } }; resource_totals: ResourceTotal[] };
  lines?: CalcLine[];
}
export interface Resource { id: number; code: string; kind: string; name: string; unit: string }

export const CONSTRUCTION_TYPES: [string, string][] = [
  ["CIVIL", "Công trình dân dụng"], ["HERITAGE", "Tu bổ, phục hồi di tích"], ["INDUSTRIAL", "Công trình công nghiệp"],
  ["HYDRO_TUNNEL", "Đường hầm thủy điện, hầm lò"], ["TRANSPORT", "Công trình giao thông"], ["TRANSPORT_TUNNEL", "Hầm giao thông"],
  ["AGRI_ENV", "Nông nghiệp và môi trường"], ["AGRI_TUNNEL", "Đường hầm (NN&MT)"], ["INFRA", "Hạ tầng kỹ thuật"],
  ["EQUIPMENT_INSTALL", "Lắp đặt thiết bị / đường dây & TBA"],
];

export const fmt = {
  money: (v: string | number | null | undefined) =>
    v === null || v === undefined || v === "" ? "" : Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 0 }),
  qty: (v: string | number | null | undefined, d = 3) =>
    v === null || v === undefined || v === "" ? "" : Number(v).toLocaleString("vi-VN", { minimumFractionDigits: 0, maximumFractionDigits: d }),
};

// ---------------------------------------------------------------- số tiền bằng chữ
const DIG = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"];
const SCALE = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"];
function group3(n: number, full: boolean): string {
  const h = Math.floor(n / 100), t = Math.floor(n / 10) % 10, u = n % 10;
  const w: string[] = [];
  if (h || full) w.push(DIG[h], "trăm");
  if (t === 0) { if (u) { if (h || full) w.push("linh"); w.push(DIG[u]); } }
  else if (t === 1) { w.push("mười"); if (u === 5) w.push("lăm"); else if (u) w.push(DIG[u]); }
  else { w.push(DIG[t], "mươi"); if (u === 1) w.push("mốt"); else if (u === 4) w.push("tư"); else if (u === 5) w.push("lăm"); else if (u) w.push(DIG[u]); }
  return w.join(" ");
}
/** 56016761 → "Năm mươi sáu triệu không trăm mười sáu nghìn bảy trăm sáu mươi mốt đồng" */
export function vndWords(v: string | number): string {
  let n = Math.round(Math.abs(Number(v)));
  if (!Number.isFinite(n)) return "";
  if (n === 0) return "Không đồng";
  const groups: number[] = [];
  while (n > 0) { groups.push(n % 1000); n = Math.floor(n / 1000); }
  const parts: string[] = [];
  for (let i = groups.length - 1; i >= 0; i--) {
    if (!groups[i]) continue;
    parts.push(group3(groups[i], i !== groups.length - 1));
    if (SCALE[i]) parts.push(SCALE[i]);
  }
  const s = (Number(v) < 0 ? "âm " : "") + parts.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1) + " đồng";
}
