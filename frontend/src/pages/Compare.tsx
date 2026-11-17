/**
 * One metric over time for the selected countries. State lives in the query string (shareable links).
 *
 * A single metric list: metrics the game keeps as yearly history (/history) use that series, which
 * also covers years before the first uploaded save; every other metric uses one point per save (/series).
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useHistory, useMetrics, useSeries } from "../api/hooks";
import type { MetricDef } from "../api/types";
import { TimeSeriesChart, type ChartSeries } from "../components/TimeSeriesChart";
import { CountryList, MetricPicker } from "../components/pickers";
import { ErrorBox, Spinner } from "../components/ui";
import { metricLabel } from "../i18n";
import { countryLabel, gameDateToYear, RANK_METRICS } from "../lib/format";
import { useCampaignCtx } from "./CampaignLayout";

/** History-only metrics have no per-save definition; they go in the economy group. */
const HISTORY_ONLY_CATEGORY = "economy";

export function Compare() {
  const { id, tags, color, players } = useCampaignCtx();
  const { data: metrics } = useMetrics();
  const [params, setParams] = useSearchParams();

  const metric = params.get("metric") || "locations";
  const isHistory = !!metrics?.history_metrics.includes(metric);
  const tagsParam = params.get("tags");
  const selected = useMemo(
    () => new Set(tagsParam !== null ? tagsParam.split(",").filter(Boolean) : tags.filter((t) => players(t).length)),
    [tagsParam, tags, players],
  );

  const allMetrics = useMemo<MetricDef[]>(() => {
    if (!metrics) return [];
    const known = new Set(metrics.metrics.map((m) => m.name));
    const extra = metrics.history_metrics
      .filter((m) => !known.has(m))
      .map((name) => ({ name, category: HISTORY_ONLY_CATEGORY, description: name }));
    return [...metrics.metrics, ...extra];
  }, [metrics]);

  const set = (patch: Record<string, string>) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(patch)) n.set(k, v);
      return n;
    }, { replace: true });

  const seriesQ = useSeries(id, metric, !!metrics && !isHistory);
  const historyQ = useHistory(id, metric, isHistory);
  const active = isHistory ? historyQ : seriesQ;

  // Every country in the response (the list shows latest values of unselected ones too).
  const allSeries = useMemo<ChartSeries[]>(() => {
    if (isHistory) {
      const hp = historyQ.data?.players ?? {};
      return Object.entries(historyQ.data?.series ?? {}).map(([tag, pts]) => ({
        key: tag,
        name: countryLabel(tag, players(tag).length ? players(tag) : hp[tag]),
        style: color(tag),
        points: pts.map(([year, y]) => ({ x: year, label: String(year), y })),
      }));
    }
    return Object.entries(seriesQ.data?.points ?? {}).map(([tag, pts]) => ({
      key: tag,
      name: countryLabel(tag, players(tag)),
      style: color(tag),
      points: pts.map(([date, y]) => ({ x: gameDateToYear(date), label: date, y })),
    }));
  }, [isHistory, seriesQ.data, historyQ.data, color, players]);

  const chartSeries = useMemo(() => allSeries.filter((s) => selected.has(s.key)), [allSeries, selected]);
  const latest = useMemo(
    () => Object.fromEntries(allSeries.map((s) => [s.key, s.points[s.points.length - 1]?.y])),
    [allSeries],
  );
  const [hover, setHover] = useState<string | null>(null);

  if (!metrics) return <Spinner />;

  const def = allMetrics.find((m) => m.name === metric);
  const rank = RANK_METRICS.has(metric);

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="card space-y-3 lg:sticky lg:top-4">
        <div>
          <span className="label">Métrica</span>
          <MetricPicker metrics={allMetrics} value={metric} onChange={(v) => set({ metric: v })} className="w-full" />
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
        <h3 className="mb-1 font-medium">{metricLabel(metric, def?.description)}</h3>
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
