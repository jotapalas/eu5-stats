/** Campaign header + tabs; shares the campaign, colours and player names with child pages. */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";

import { keys, useCampaign } from "../api/hooks";
import type { CampaignDetail } from "../api/types";
import { ErrorBox, Spinner, StatusBadge } from "../components/ui";
import { colorScale, useDarkMode, type ColorScale } from "../lib/colors";

export interface CampaignCtx {
  campaign: CampaignDetail;
  id: number;
  color: ColorScale;
  /** Players of a country in its latest snapshot ([] for AI). */
  players: (tag: string) => string[];
  /** Every country with data, sorted. */
  tags: string[];
}

export const useCampaignCtx = () => useOutletContext<CampaignCtx>();

const TABS = [
  { to: "", label: "Ranking", end: true },
  { to: "compare", label: "Comparativa" },
  { to: "sessions", label: "Sesiones" },
  { to: "settings", label: "Ajustes" },
];

export function CampaignLayout() {
  const id = Number(useParams().id);
  const { data: campaign, error, isLoading } = useCampaign(id);
  const dark = useDarkMode();
  const qc = useQueryClient();

  // When the worker finishes saves, refresh every derived view (series, sessions, ...).
  const done = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!campaign) return;
    if (done.current !== undefined && done.current !== campaign.saves_done) {
      qc.invalidateQueries({ queryKey: keys.campaign(id), predicate: (q) => q.queryKey.length > 2 });
      qc.invalidateQueries({ queryKey: keys.campaigns });
    }
    done.current = campaign.saves_done;
  }, [campaign, id, qc]);

  const ctx = useMemo<CampaignCtx | null>(() => {
    if (!campaign) return null;
    const tags = [...new Set([...Object.keys(campaign.latest), ...campaign.countries])].sort();
    return {
      campaign,
      id,
      tags,
      color: colorScale(tags, dark),
      players: (tag) => campaign.latest[tag]?.players ?? [],
    };
  }, [campaign, id, dark]);

  if (isLoading) return <Spinner />;
  if (error || !ctx || !campaign) return <ErrorBox error={error ?? "Campaña no encontrada"} />;

  return (
    <div>
      <div className="mb-4">
        <div className="text-xs muted">
          <Link to="/" className="hover:underline">Campañas</Link> /
        </div>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-xl font-semibold">{campaign.name}</h1>
          <span className="text-sm muted">
            {campaign.first_date ? `${campaign.first_date} → ${campaign.last_date}` : "Sin saves procesados"}
          </span>
          <span className="flex gap-1.5">
            <StatusBadge status="done" count={campaign.saves_done} />
            {campaign.saves_pending > 0 && <StatusBadge status="processing" count={campaign.saves_pending} />}
            {campaign.saves_error > 0 && <StatusBadge status="error" count={campaign.saves_error} />}
          </span>
        </div>
        {campaign.description && <p className="mt-1 text-sm muted">{campaign.description}</p>}
      </div>
      <nav className="mb-5 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                isActive
                  ? "border-indigo-600 text-indigo-700 dark:text-indigo-400"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet context={ctx} />
    </div>
  );
}
