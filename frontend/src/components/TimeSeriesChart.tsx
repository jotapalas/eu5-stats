/**
 * Multi-series line chart over a numeric x axis (fractional game year or plain year).
 * One point per save; crosshair tooltip sorted by value; legend toggles and highlights series;
 * direct end labels when there are at most four series; a table view for exact values.
 */
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { chartChrome, useDarkMode, type SeriesStyle } from "../lib/colors";
import { formatValue } from "../lib/format";
import { Swatch } from "./ui-swatch";

export interface ChartPoint {
  x: number;
  /** Label shown for this x (game date "1367.1.5" or year). */
  label: string;
  y: number;
}

export interface ChartSeries {
  key: string;
  name: string;
  style: SeriesStyle;
  points: ChartPoint[];
}

type Row = { x: number; label: string } & Record<string, number | string>;

interface Props {
  series: ChartSeries[];
  height?: number;
  /** Compact mode for small multiples: no legend, no table toggle, fewer ticks. */
  compact?: boolean;
  xTick?: (x: number) => string;
  /**
   * Rank metric (1 = best): reversed log Y axis so the leader is on top and ranks 1-20 stay apart
   * from the ~2000 tail. Values <= 0 (no rank; Paradox writes 0) are dropped.
   */
  rank?: boolean;
  /** Render the built-in legend below the chart (off when the page shows its own country list). */
  legend?: boolean;
  /** Series to highlight, controlled from outside (e.g. hovering a row of an external list). */
  highlight?: string | null;
}

export function TimeSeriesChart({ series: input, height = 380, compact = false, rank = false, legend: showLegend = true,
                                  highlight = null, xTick = (x) => String(Math.floor(x)) }: Props) {
  const dark = useDarkMode();
  const chrome = chartChrome(dark);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hoverInner, setHover] = useState<string | null>(null);
  const hover = highlight ?? hoverInner;
  const [asTable, setAsTable] = useState(false);

  const series = useMemo(
    () => (rank ? input.map((s) => ({ ...s, points: s.points.filter((p) => p.y > 0) })) : input),
    [input, rank],
  );

  // Axis from rank 1 down to the worst rank shown, ticked at powers of ten (1, 10, 100, 1000...).
  const rankAxis = useMemo(() => {
    if (!rank) return undefined;
    const max = Math.max(10, ...series.flatMap((s) => s.points.map((p) => p.y)));
    const ticks = Array.from({ length: Math.floor(Math.log10(max)) + 1 }, (_, i) => 10 ** i);
    // Headroom below the worst rank so its line and the last tick are not drawn on the edge.
    return { max: max * 1.4, ticks };
  }, [series, rank]);

  const { rows, lastIndex, domain, ticks } = useMemo(() => {
    const byX = new Map<number, Row>();
    for (const s of series)
      for (const p of s.points) {
        const row = byX.get(p.x) ?? ({ x: p.x, label: p.label } as Row);
        row[s.key] = p.y;
        byX.set(p.x, row);
      }
    const rows = [...byX.values()].sort((a, b) => a.x - b.x);
    const lastIndex: Record<string, number> = {};
    rows.forEach((r, i) => series.forEach((s) => {
      if (s.key in r) lastIndex[s.key] = i;
    }));
    const xs = rows.map((r) => r.x);
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    // A single save would collapse the axis; pad it to a year either side.
    const domain: [number, number] = rows.length === 0 ? [0, 1] : lo === hi ? [lo - 1, hi + 1] : [Math.floor(lo), hi];
    // Ticks on whole years: domains start at fractional game dates (1338.2.1), which skips years otherwise.
    const first = Math.ceil(domain[0]);
    const span = Math.floor(domain[1]) - first;
    const step = Math.max(1, Math.ceil(span / 10));
    const ticks = span >= 0 ? Array.from({ length: Math.floor(span / step) + 1 }, (_, i) => first + i * step) : undefined;
    return { rows, lastIndex, domain, ticks };
  }, [series]);

  const visible = series.filter((s) => !hidden.has(s.key));
  const directLabels = !compact && visible.length <= 4;
  const latest = (s: ChartSeries) => s.points[s.points.length - 1]?.y;
  // Best first: highest value, or lowest rank.
  const legend = [...series].sort((a, b) =>
    rank ? (latest(a) ?? Infinity) - (latest(b) ?? Infinity) : (latest(b) ?? -Infinity) - (latest(a) ?? -Infinity));

  const toggle = (key: string) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });

  if (!rows.length) return <div className="py-10 text-center text-sm muted">Sin datos</div>;

  return (
    <div>
      {!compact && (
        <div className="mb-2 flex justify-end">
          <button type="button" className="btn btn-sm" onClick={() => setAsTable((v) => !v)}>
            {asTable ? "Ver gráfica" : "Ver tabla"}
          </button>
        </div>
      )}
      {asTable ? (
        <DataTable rows={rows} series={visible} />
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={rows} margin={{ top: 8, right: directLabels ? 48 : 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chrome.grid} vertical={false} />
            <XAxis
              dataKey="x"
              type="number"
              domain={domain}
              tickFormatter={xTick}
              stroke={chrome.axis}
              tick={{ fill: chrome.text, fontSize: 11 }}
              ticks={ticks}
              allowDecimals={false}
              hide={compact}
            />
            <YAxis
              tickFormatter={formatValue}
              stroke={chrome.axis}
              tick={{ fill: chrome.text, fontSize: 11 }}
              width={compact ? 44 : 56}
              axisLine={false}
              tickLine={false}
              {...(rankAxis
                ? {
                    reversed: true,
                    scale: "log" as const,
                    domain: [1, rankAxis.max],
                    ticks: rankAxis.ticks,
                    interval: 0,
                    allowDataOverflow: true,
                  }
                : { tickCount: compact ? 3 : 6 })}
            />
            <Tooltip
              cursor={{ stroke: chrome.axis, strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as Row;
                const items = payload
                  .filter((p) => typeof p.value === "number")
                  // Same order as the axis: best first (lowest rank on rank charts).
                  .sort((a, b) => (rank ? 1 : -1) * (Number(a.value) - Number(b.value)));
                return (
                  <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900">
                    <div className="mb-1 font-medium">{row.label}</div>
                    {items.map((p) => {
                      const s = series.find((s) => s.key === p.dataKey);
                      return (
                        <div key={String(p.dataKey)} className="flex items-center gap-2">
                          {s && <Swatch style={s.style} />}
                          <span className="flex-1 text-slate-600 dark:text-slate-300">{s?.name ?? String(p.dataKey)}</span>
                          <span className="font-medium tabular-nums">{formatValue(Number(p.value))}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              }}
            />
            {visible.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.name}
                stroke={s.style.color}
                strokeDasharray={s.style.dash}
                strokeWidth={hover === s.key ? 3 : 2}
                strokeOpacity={hover && hover !== s.key ? 0.15 : 1}
                dot={rows.length <= 24 ? { r: 3, strokeWidth: 0, fill: s.style.color } : false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: dark ? "#1a1a19" : "#fcfcfb" }}
                connectNulls
                isAnimationActive={false}
                label={
                  directLabels
                    ? (p: { index?: number; x?: number; y?: number }) =>
                        p.index === lastIndex[s.key] ? (
                          <text key={s.key} x={(p.x ?? 0) + 6} y={(p.y ?? 0) + 4} fontSize={11} fill={chrome.text}>
                            {s.key}
                          </text>
                        ) : (
                          <g key={`${s.key}-${p.index}`} />
                        )
                    : undefined
                }
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
      {showLegend && !compact && series.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-1.5" onMouseLeave={() => setHover(null)}>
          {legend.map((s) => {
            const off = hidden.has(s.key);
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => toggle(s.key)}
                onMouseEnter={() => !off && setHover(s.key)}
                className={`flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${
                  off ? "border-dashed border-slate-300 opacity-50 dark:border-slate-700" : "border-slate-200 dark:border-slate-700"
                }`}
                title={off ? "Mostrar" : "Ocultar"}
              >
                <Swatch style={s.style} />
                <span>{s.name}</span>
                <span className="tabular-nums muted">{formatValue(latest(s))}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DataTable({ rows, series }: { rows: Row[]; series: ChartSeries[] }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="table-base">
        <thead className="sticky top-0 bg-white dark:bg-slate-900">
          <tr>
            <th>Fecha</th>
            {series.map((s) => (
              <th key={s.key} className="num">{s.key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.x}>
              <td>{r.label}</td>
              {series.map((s) => (
                <td key={s.key} className="num">{formatValue(r[s.key] as number | undefined)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
