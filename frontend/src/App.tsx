import { Link, Route, Routes } from "react-router-dom";

import { CampaignLayout } from "./pages/CampaignLayout";
import { CampaignList } from "./pages/CampaignList";
import { Compare } from "./pages/Compare";
import { Country } from "./pages/Country";
import { Overview } from "./pages/Overview";
import { SessionDetail } from "./pages/SessionDetail";
import { Sessions } from "./pages/Sessions";
import { Settings } from "./pages/Settings";
import { READONLY } from "./lib/mode";
import { setDarkMode, useDarkMode } from "./lib/colors";
import { THEME_LABELS } from "./i18n";

function ThemeToggle() {
  const dark = useDarkMode();
  const label = dark ? THEME_LABELS.light : THEME_LABELS.dark;
  return (
    <button type="button" className="btn btn-sm ml-auto" onClick={() => setDarkMode(!dark)} title={label} aria-label={label}>
      <span aria-hidden>{dark ? "☀" : "☾"}</span>
      {label}
    </button>
  );
}

export function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <Link to="/" className="text-base font-semibold tracking-tight">
            EU5 Stats
          </Link>
          <span className="text-xs muted">Estadísticas de campañas multijugador</span>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<CampaignList />} />
          <Route path="/c/:id" element={<CampaignLayout />}>
            <Route index element={<Overview />} />
            <Route path="compare" element={<Compare />} />
            <Route path="country/:tag" element={<Country />} />
            <Route path="sessions" element={<Sessions />} />
            <Route path="sessions/:sid" element={<SessionDetail />} />
            {!READONLY && <Route path="settings" element={<Settings />} />}
          </Route>
          <Route path="*" element={<p className="muted">Página no encontrada.</p>} />
        </Routes>
      </main>
    </div>
  );
}
