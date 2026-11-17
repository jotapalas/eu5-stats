/**
 * One metric over time for the selected countries. State lives in the query string (shareable links).
 *
 * A single metric list: metrics the game keeps as yearly history (/history) use that series, which
 * also covers years before the first uploaded save; every other metric uses one point per save (/series).
 */
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useHistory, useMetrics, useSeries } from "../api/hooks";
import type { MetricDef } from "../api/types";
import { TimeSeriesChart, type ChartSeries } from "../components/TimeSeriesChart";
import { CountryMultiSelect, MetricPicker } from "../components/pickers";
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

  const chartSeries = useMemo<ChartSeries[]>(() => {
    if (isHistory) {
      const hp = historyQ.data?.players ?? {};
      return Object.entries(historyQ.data?.series ?? {})
        .filter(([tag]) => selected.has(tag))
        .map(([tag, pts]) => ({
          key: tag,
          name: countryLabel(tag, hp[tag] ?? players(tag)),
          style: color(tag),
          points: pts.map(([year, y]) => ({ x: year, label: String(year), y })),
        }));
    }
    return Object.entries(seriesQ.data?.points ?? {})
      .filter(([tag]) => selected.has(tag))
      .map(([tag, pts]) => ({
        key: tag,
        name: countryLabel(tag, players(tag)),
        style: color(tag),
        points: pts.map(([date, y]) => ({ x: gameDateToYear(date), label: date, y })),
      }));
  }, [isHistory, seriesQ.data, historyQ.data, selected, color, players]);

  if (!metrics) return <Spinner />;

  const def = allMetrics.find((m) => m.name === metric);

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <span className="label">Métrica</span>
            <MetricPicker metrics={allMetrics} value={metric} onChange={(v) => set({ metric: v })} />
          </div>
        </div>
        <div>
          <span className="label">Países</span>
          <CountryMultiSelect
            tags={tags}
            selected={selected}
            onChange={(s) => set({ tags: [...s].sort().join(",") })}
            color={color}
            players={players}
          />
        </div>
      </div>
      <div className="card">
        <h3 className="mb-1 font-medium">{metricLabel(metric, def?.description)}</h3>
        <ErrorBox error={active.error} />
        {active.isLoading ? (
          <Spinner />
        ) : selected.size === 0 ? (
          <p className="py-10 text-center text-sm muted">Selecciona al menos un país.</p>
        ) : (
          <TimeSeriesChart series={chartSeries} rank={RANK_METRICS.has(metric)} />
        )}
      </div>
    </div>
  );
}
