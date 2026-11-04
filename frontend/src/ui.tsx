import { createContext, ReactNode, useCallback, useContext, useState } from "react";

type Toast = { msg: string; err?: boolean } | null;
const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast>(null);
  const show = useCallback((msg: string, err?: boolean) => {
    setToast({ msg, err });
    window.setTimeout(() => setToast((t) => (t && t.msg === msg ? null : t)), err ? 6000 : 3000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={`toast ${toast.err ? "err" : ""}`} role="status">{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

export function Modal({ title, children, onClose, footer, wide }: { title: string; children: ReactNode; onClose: () => void; footer?: ReactNode; wide?: boolean }) {
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-label={title}>
        <header>{title}</header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function errMsg(e: unknown): string {
  if (e && typeof e === "object" && "data" in e) {
    const d = (e as { data: unknown }).data;
    if (d && typeof d === "object") {
      return Object.entries(d as Record<string, unknown>)
        .map(([k, v]) => (k === "detail" ? String(v) : `${k}: ${Array.isArray(v) ? v.join(", ") : JSON.stringify(v)}`))
        .join(" · ");
    }
  }
  return e instanceof Error ? e.message : String(e);
}
