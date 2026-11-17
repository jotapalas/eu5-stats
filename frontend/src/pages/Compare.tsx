/**
 * One metric over time for the selected countries. State lives in the query string (shareable links).
 *
 * One point per save (/series). Metrics with vassal variants show the "Incluir vasallos" selector
 * (`vassals` param).
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useMetrics, useSeries } from "../api/hooks";
import { TimeSeriesChart, type ChartSeries } from "../components/TimeSeriesChart";
import { CountryList, MetricPicker, VassalScopePicker } from "../components/pickers";
import { ErrorBox, Spinner } from "../components/ui";
import { metricLabel, VASSAL_SCOPE_SUFFIX } from "../i18n";
import { countryLabel, gameDateToYear, RANK_METRICS } from "../lib/format";
import { hasVassalVariant, resolveMetric, useVassalScope } from "../lib/vassals";
import { useCampaignCtx } from "./CampaignLayout";

export function Compare() {
  const { id, tags, color, players } = useCampaignCtx();
  const { data: metrics } = useMetrics();
  const [params, setParams] = useSearchParams();

  const metric = params.get("metric") || "locations";
  const [scopeParam, setScope] = useVassalScope();
  const hasVassals = hasVassalVariant(metrics?.vassal_metrics, metric);
  const scope = hasVassals ? scopeParam : "none";
  const effective = resolveMetric(metrics?.vassal_metrics, metric, scope);
  const tagsParam = params.get("tags");
  const selected = useMemo(
    () => new Set(tagsParam !== null ? tagsParam.split(",").filter(Boolean) : tags.filter((t) => players(t).length)),
    [tagsParam, tags, players],
  );

  const set = (patch: Record<string, string>) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(patch)) n.set(k, v);
      return n;
    }, { replace: true });

  const active = useSeries(id, effective, !!metrics);

  // Every country in the response (the list shows latest values of unselected ones too).
  const allSeries = useMemo<ChartSeries[]>(
    () =>
      Object.entries(active.data?.points ?? {}).map(([tag, pts]) => ({
        key: tag,
        name: countryLabel(tag, players(tag)),
        style: color(tag),
        points: pts.map(([date, y]) => ({ x: gameDateToYear(date), label: date, y })),
      })),
    [active.data, color, players],
  );

  const chartSeries = useMemo(() => allSeries.filter((s) => selected.has(s.key)), [allSeries, selected]);
  const latest = useMemo(
    () => Object.fromEntries(allSeries.map((s) => [s.key, s.points[s.points.length - 1]?.y])),
    [allSeries],
  );
  const [hover, setHover] = useState<string | null>(null);

  if (!metrics) return <Spinner />;

  const def = metrics.metrics.find((m) => m.name === metric);
  const rank = RANK_METRICS.has(metric);

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="card space-y-3 lg:sticky lg:top-4">
        <div>
          <span className="label">Métrica</span>
          <MetricPicker metrics={metrics.metrics} value={metric} onChange={(v) => set({ metric: v })} className="w-full" />
          {hasVassals && (
            <div className="mt-2">
              <VassalScopePicker value={scope} onChange={setScope} />
            </div>
          )}
        </div>
        <div>
          <span className="label">Países</span>
          <CountryList
            tags={tags}
            selected={selected}
            onChange={(s) => set({ tags: [...s].sort().join(",") })}
            color={color}
            players={players}
            latest={latest}
            rank={rank}
            onHover={setHover}
          />
        </div>
      </div>
      <div className="card min-w-0">
        <h3 className="mb-1 font-medium">{metricLabel(metric, def?.description)}{VASSAL_SCOPE_SUFFIX[scope]}</h3>
        <ErrorBox error={active.error} />
        {active.isLoading ? (
          <Spinner />
        ) : selected.size === 0 ? (
          <p className="py-10 text-center text-sm muted">Selecciona al menos un país.</p>
        ) : (
          <TimeSeriesChart series={chartSeries} rank={rank} legend={false} highlight={hover} height={520} />
        )}
      </div>
    </div>
  );
}
