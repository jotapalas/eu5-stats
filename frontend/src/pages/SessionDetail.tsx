/** One session: its saves (status, errors) and what changed between its first and last save. */
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useDeleteSession, useMetrics, useReprocessSave, useSession, useSessionSummary } from "../api/hooks";
import { MetricPicker } from "../components/pickers";
import { ErrorBox, PageTitle, Spinner, StatusBadge } from "../components/ui";
import { Swatch } from "../components/ui-swatch";
import { metricLabel } from "../i18n";
import { countryLabel, deltaTone, formatDelta, formatValue, LOWER_IS_BETTER } from "../lib/format";
import { useCampaignCtx } from "./CampaignLayout";
import { UploadForm } from "./Sessions";

export function SessionDetail() {
  const sid = Number(useParams().sid);
  const { id } = useCampaignCtx();
  const { data: session, error, isLoading } = useSession(id, sid);
  const del = useDeleteSession(id);
  const reprocess = useReprocessSave(id);
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);

  if (isLoading) return <Spinner />;
  if (error || !session) return <ErrorBox error={error} />;

  const remove = () => {
    if (confirm(`¿Borrar la sesión «${session.name || session.id}» y sus ${session.saves} saves? Sus estadísticas desaparecerán.`))
      del.mutate(sid, { onSuccess: () => navigate(`/c/${id}/sessions`) });
  };

  return (
    <div className="space-y-5">
      <PageTitle
        actions={
          <>
            <button className="btn" onClick={() => setAdding((v) => !v)}>Añadir saves</button>
            <button className="btn btn-danger" onClick={remove} disabled={del.isPending}>Borrar sesión</button>
          </>
        }
      >
        {session.name || `Sesión ${session.id}`}
        <span className="ml-2 text-sm font-normal muted">
          {session.played_on && `jugada el ${session.played_on} · `}
          {session.first_date ? `${session.first_date} → ${session.last_date}` : "sin saves procesados"}
        </span>
      </PageTitle>
      {session.notes && <p className="text-sm muted">{session.notes}</p>}
      <ErrorBox error={del.error ?? reprocess.error} />
      {adding && <UploadForm campaignId={id} sessionId={sid} />}

      <Summary sid={sid} />

      <div className="card overflow-x-auto p-0">
        <table className="table-base">
          <thead>
            <tr>
              <th>Fichero</th>
              <th>Fecha de juego</th>
              <th>Versión</th>
              <th>Estado</th>
              <th>Detalle</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {session.save_list.map((s) => (
              <tr key={s.id}>
                <td className="max-w-[18rem] truncate" title={s.sha256}>{s.file_name}</td>
                <td>{s.game_date ?? "–"}</td>
                <td>{s.version ?? "–"}</td>
                <td><StatusBadge status={s.status} /></td>
                <td className="max-w-[24rem] whitespace-normal text-xs">
                  {s.error && <span className="text-red-700 dark:text-red-400">{s.error}</span>}
                  {s.warning && <span className="text-amber-700 dark:text-amber-400">{s.warning}</span>}
                </td>
                <td className="text-right">
                  <button className="btn btn-sm" onClick={() => reprocess.mutate(s.id)} disabled={s.status === "pending" || s.status === "processing"}>
                    Reprocesar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Summary({ sid }: { sid: number }) {
  const { id, color, players } = useCampaignCtx();
  const { data, error, isLoading } = useSessionSummary(id, sid);
  const { data: metrics } = useMetrics();
  const [metric, setMetric] = useState("locations");

  const rows = useMemo(() => {
    const lower = LOWER_IS_BETTER.has(metric);
    return Object.entries(data?.countries ?? {})
      .map(([tag, ms]) => ({ tag, ...(ms[metric] ?? { start: null, end: null, delta: null }) }))
      .sort((a, b) => ((b.delta ?? -Infinity) - (a.delta ?? -Infinity)) * (lower ? -1 : 1));
  }, [data, metric]);

  if (isLoading || !metrics) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.first_date) return null;

  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.delta ?? 0)), 0) || 1;

  return (
    <div className="card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-medium">
          Cambios en la sesión <span className="text-sm font-normal muted">{data.first_date} → {data.last_date}</span>
        </h3>
        <MetricPicker metrics={metrics.metrics} value={metric} onChange={setMetric} />
      </div>
      <table className="table-base">
        <thead>
          <tr>
            <th>País</th>
            <th className="num">Inicio</th>
            <th className="num">Final</th>
            <th className="num">Cambio</th>
            <th className="w-1/3" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const tone = deltaTone(metric, r.delta);
            const width = `${(Math.abs(r.delta ?? 0) / maxAbs) * 50}%`;
            return (
              <tr key={r.tag}>
                <td>
                  <span className="flex items-center gap-2">
                    <Swatch style={color(r.tag)} />
                    {countryLabel(r.tag, players(r.tag))}
                  </span>
                </td>
                <td className="num">{formatValue(r.start)}</td>
                <td className="num">{formatValue(r.end)}</td>
                <td className={`num font-medium ${tone === "good" ? "text-emerald-700 dark:text-emerald-400" : tone === "bad" ? "text-red-700 dark:text-red-400" : ""}`}>
                  {formatDelta(r.delta)}
                </td>
                <td>
                  {/* Diverging bar around a neutral centre line. */}
                  <div className="relative h-3">
                    <div className="absolute left-1/2 top-0 h-full w-px bg-slate-300 dark:bg-slate-700" />
                    {!!r.delta && (
                      <div
                        className={`absolute top-0.5 h-2 rounded-sm ${tone === "good" ? "bg-emerald-500" : "bg-red-500"}`}
                        style={r.delta > 0 ? { left: "50%", width } : { right: "50%", width }}
                      />
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs muted">{metricLabel(metric)}: primero frente a último save procesado de la sesión.</p>
    </div>
  );
}
