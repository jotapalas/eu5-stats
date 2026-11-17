/** Current ranking: latest snapshot of every country, sortable by any metric. */
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useMetrics } from "../api/hooks";
import type { Snapshot } from "../api/types";
import { VassalScopePicker } from "../components/pickers";
import { Empty, Segmented, Spinner } from "../components/ui";
import { Swatch } from "../components/ui-swatch";
import { categoryLabel, metricLabel } from "../i18n";
import { formatValue, LOWER_IS_BETTER } from "../lib/format";
import { READONLY } from "../lib/mode";
import { resolveMetric, scopeQuery, useVassalScope } from "../lib/vassals";
import { useCampaignCtx } from "./CampaignLayout";

/** `values`: each base metric resolved for the vassal scope. */
type Row = Snapshot & { label: string; values: Record<string, number | undefined> };
const col = createColumnHelper<Row>();

export function Overview() {
  const { campaign, color, id, players } = useCampaignCtx();
  const { data: metrics } = useMetrics();
  const navigate = useNavigate();
  const [category, setCategory] = useState("all");
  const [onlyPlayers, setOnlyPlayers] = useState(false);
  const [scope, setScope] = useVassalScope();
  const [sorting, setSorting] = useState<SortingState>([{ id: "score_place", desc: false }]);

  // The scope is resolved in the data, not in the accessors: TanStack caches cell values per row and column
  // id and only rebuilds rows when `data` changes, so a new accessor alone would keep showing stale values.
  const rows = useMemo<Row[]>(
    () =>
      Object.entries(campaign.latest)
        .map(([label, s]) => ({
          ...s,
          label,
          values: Object.fromEntries(
            (metrics?.metrics ?? []).map((m) => [m.name, s.metrics[resolveMetric(metrics?.vassal_metrics, m.name, scope)]]),
          ),
        }))
        .filter((r) => !onlyPlayers || players(r.label).length),
    [campaign.latest, onlyPlayers, players, metrics, scope],
  );

  const columns = useMemo(() => {
    if (!metrics) return [];
    return [
      col.accessor("label", {
        header: "País",
        cell: (c) => (
          <span className="flex items-center gap-2">
            <Swatch style={color(c.getValue())} />
            <span className="font-medium">{c.getValue()}</span>
            <span className="max-w-[16rem] truncate muted">{players(c.getValue()).join(", ") || "IA"}</span>
          </span>
        ),
      }),
      ...metrics.metrics.map((m) =>
        // Column ids stay the base name so sorting survives scope changes.
        col.accessor((r) => r.values[m.name] ?? null, {
          id: m.name,
          header: metricLabel(m.name, m.description),
          meta: { description: m.description, category: m.category },
          sortDescFirst: !LOWER_IS_BETTER.has(m.name),
          sortUndefined: "last",
          cell: (c) => formatValue(c.getValue()),
        }),
      ),
    ];
  }, [metrics, color, players]);

  const columnVisibility = useMemo(
    () => Object.fromEntries((metrics?.metrics ?? []).map((m) => [m.name, category === "all" || m.category === category])),
    [metrics, category],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!metrics) return <Spinner />;
  if (!Object.keys(campaign.latest).length)
    return (
      <Empty>
        Aún no hay estadísticas.{" "}
        {!READONLY && <><Link to="sessions" className="text-indigo-600 hover:underline">Sube una sesión</Link> para empezar.</>}
      </Empty>
    );

  const categories = [...new Set(metrics.metrics.map((m) => m.category))];
  const stale = (r: Row) => r.date !== campaign.last_date;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Segmented
          value={category}
          onChange={setCategory}
          options={[{ value: "all", label: "Todas" }, ...categories.map((c) => ({ value: c, label: categoryLabel(c) }))]}
        />
        <VassalScopePicker value={scope} onChange={setScope} />
        <span className="text-xs muted">Último dato de cada país · clic en una fila para ver su ficha</span>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="table-base">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted();
                  const meta = h.column.columnDef.meta as { description?: string } | undefined;
                  return (
                    <th
                      key={h.id}
                      className={`cursor-pointer select-none ${h.column.id === "label" ? "sticky left-0 bg-white dark:bg-slate-900" : "num"}`}
                      onClick={h.column.getToggleSortingHandler()}
                      title={meta?.description}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => (
              <tr key={r.id} className="cursor-pointer" onClick={() => navigate(`/c/${id}/country/${r.original.label}${scopeQuery(scope, "?")}`)}>
                {r.getVisibleCells().map((c) => (
                  <td
                    key={c.id}
                    className={c.column.id === "label" ? "sticky left-0 bg-white dark:bg-slate-900" : "num"}
                    title={c.column.id === "label" && stale(r.original) ? `Último dato: ${r.original.date}` : undefined}
                  >
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                    {c.column.id === "label" && stale(r.original) && (
                      <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">({r.original.date})</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
