import { FormEvent, useState } from "react";
import { api } from "./api";
import { errMsg } from "./ui";

export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.login(u, p); onDone(); }
    catch (e) { setErr(errMsg(e).includes("credentials") || errMsg(e).includes("non_field") ? "Sai tên đăng nhập hoặc mật khẩu" : errMsg(e)); }
    finally { setBusy(false); }
  };
  return (
    <>
      <div className="titlebar"><div className="logo">SE</div><div className="doc">SmartEstimator — Dự toán xây dựng</div></div>
      <div className="page"><div className="center">
        <form className="card login" onSubmit={submit}>
          <h1>Đăng nhập</h1>
          <p className="doc-sub">Lập dự toán theo định mức và đơn giá xây dựng Việt Nam</p>
          <div className="field"><label htmlFor="u">Tên đăng nhập</label><input id="u" autoFocus value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></div>
          <div className="field"><label htmlFor="p">Mật khẩu</label><input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></div>
          {err && <div className="error">{err}</div>}
          <button className="btn primary" style={{ width: "100%" }} disabled={busy || !u || !p}>{busy ? "Đang đăng nhập…" : "Đăng nhập"}</button>
        </form>
      </div></div>
    </>
  );
}
