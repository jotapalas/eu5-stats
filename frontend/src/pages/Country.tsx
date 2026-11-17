/** Country sheet: players, tag changes and small multiples of every metric. */
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { useCountry, useMetrics } from "../api/hooks";
import { VassalScopePicker } from "../components/pickers";
import { TimeSeriesChart } from "../components/TimeSeriesChart";
import { ErrorBox, PageTitle, Spinner } from "../components/ui";
import { Swatch } from "../components/ui-swatch";
import { categoryLabel, metricLabel } from "../i18n";
import { deltaTone, formatDelta, formatValue, gameDateToYear, RANK_METRICS } from "../lib/format";
import { hasVassalVariant, resolveMetric, scopeQuery, useVassalScope } from "../lib/vassals";
import { useCampaignCtx } from "./CampaignLayout";

const TONE = { good: "text-emerald-700 dark:text-emerald-400", bad: "text-red-700 dark:text-red-400", neutral: "muted" };

export function Country() {
  const tag = (useParams().tag ?? "").toUpperCase();
  const { id, color, players: mainPlayers } = useCampaignCtx();
  const { data, error, isLoading } = useCountry(id, tag);
  const { data: metrics } = useMetrics();
  const [scope, setScope] = useVassalScope();

  const info = useMemo(() => {
    const tl = data?.timeline ?? [];
    const players: string[] = [];
    const tags: { tag: string; from: string }[] = [];
    for (const e of tl) {
      for (const p of e.players) if (!players.includes(p)) players.push(p);
      if (e.tag && tags[tags.length - 1]?.tag !== e.tag) tags.push({ tag: e.tag, from: e.date });
    }
    return { players, tags, first: tl[0], last: tl[tl.length - 1] };
  }, [data]);

  if (isLoading || !metrics) return <Spinner />;
  if (error || !data) return <ErrorBox error={error} />;

  const style = color(data.tag);
  const categories = [...new Set(metrics.metrics.map((m) => m.category))];

  return (
    <div>
      <PageTitle
        actions={
          <>
            <VassalScopePicker value={scope} onChange={setScope} />
            <Link className="btn" to={`/c/${id}/compare?tags=${data.tag}${scopeQuery(scope)}`}>
              Comparar con otros
            </Link>
          </>
        }
      >
        <span className="flex items-center gap-2">
          <Swatch style={style} />
          {data.tag}
          <span className="text-sm font-normal muted">{mainPlayers(data.tag).join(", ") || "IA"}</span>
        </span>
      </PageTitle>
      <div className="mb-5 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span><span className="muted">Datos:</span> {info.first?.date} - {info.last?.date} ({data.timeline.length} saves)</span>
        {info.players.length > 0 && (
          <span><span className="muted">Jugadores en los saves:</span> {info.players.join(", ")}</span>
        )}
        {info.tags.length > 1 && (
          <span>
            <span className="muted">Tags:</span> {info.tags.map((t) => `${t.tag} (desde ${t.from})`).join(" - ")}
          </span>
        )}
      </div>
      {categories.map((cat) => (
        <section key={cat} className="mb-6">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide muted">{categoryLabel(cat)}</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {metrics.metrics
              .filter((m) => m.category === cat)
              .map((m) => {
                const name = resolveMetric(metrics.vassal_metrics, m.name, scope);
                const withVassals = name !== m.name;
                const points = data.timeline
                  .filter((e) => name in e.metrics)
                  .map((e) => ({ x: gameDateToYear(e.date), label: e.date, y: e.metrics[name] }));
                const last = points[points.length - 1]?.y;
                const delta = points.length > 1 ? last - points[0].y : null;
                return (
                  <Link
                    key={m.name}
                    to={`/c/${id}/compare?metric=${m.name}&tags=${data.tag}${hasVassalVariant(metrics.vassal_metrics, m.name) ? scopeQuery(scope) : ""}`}
                    className="card block p-3 transition hover:border-indigo-400"
                    title={m.description}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm">
                        {metricLabel(m.name, m.description)}
                        {withVassals && <span className="muted"> + vas.</span>}
                      </span>
                      <span className="text-right">
                        <span className="font-semibold tabular-nums">{formatValue(last)}</span>
                        {delta !== null && (
                          <span className={`ml-1.5 text-xs tabular-nums ${TONE[deltaTone(m.name, delta)]}`}>{formatDelta(delta)}</span>
                        )}
                      </span>
                    </div>
                    {points.length > 1 && (
                      <TimeSeriesChart compact height={90} rank={RANK_METRICS.has(m.name)} series={[{ key: data.tag, name: data.tag, style, points }]} />
                    )}
                  </Link>
                );
              })}
          </div>
        </section>
      ))}
    </div>
  );
}
