import { useEffect, useState } from "react";
import { getToken, setToken } from "./api";
import Login from "./Login";
import Projects from "./Projects";
import Workbook from "./Workbook";
import { ToastProvider } from "./ui";

type Route = { name: "projects"; tab?: "open" | "new" | "data" } | { name: "workbook"; projectId: number; revisionId?: number };

function parseHash(): Route {
  const m = /^#\/p\/(\d+)(?:\/r\/(\d+))?/.exec(window.location.hash);
  if (m) return { name: "workbook", projectId: Number(m[1]), revisionId: m[2] ? Number(m[2]) : undefined };
  const h = window.location.hash;
  return { name: "projects", tab: h.startsWith("#/du-lieu") ? "data" : h.startsWith("#/moi") ? "new" : "open" };
}

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [route, setRoute] = useState<Route>(parseHash);

  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const logout = () => { setToken(null); setAuthed(false); };

  return (
    <ToastProvider>
      <div className="app">
        {!authed ? (
          <Login onDone={() => setAuthed(true)} />
        ) : route.name === "workbook" ? (
          <Workbook key={`${route.projectId}-${route.revisionId ?? ""}`} projectId={route.projectId} revisionId={route.revisionId} onLogout={logout} />
        ) : (
          <Projects key={route.tab} initialTab={route.tab} onLogout={logout} />
        )}
      </div>
    </ToastProvider>
  );
}
