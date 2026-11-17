/** Sessions of a campaign and the upload form for a new one. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { useSessions, useUpload } from "../api/hooks";
import type { UploadResult } from "../api/types";
import { FileDropzone } from "../components/pickers";
import { Empty, ErrorBox, PageTitle, Spinner, StatusBadge } from "../components/ui";
import { READONLY } from "../lib/mode";
import { useCampaignCtx } from "./CampaignLayout";

export function Sessions() {
  const { id } = useCampaignCtx();
  const { data, error, isLoading } = useSessions(id);
  const [open, setOpen] = useState(false);

  return (
    <div>
      <PageTitle actions={!READONLY && <button className="btn btn-primary" onClick={() => setOpen((v) => !v)}>Subir sesión</button>}>
        Sesiones
      </PageTitle>
      {!READONLY && (open || data?.length === 0) && <UploadForm campaignId={id} />}
      {isLoading && <Spinner />}
      <ErrorBox error={error} />
      {data && data.length === 0 && <Empty>No hay sesiones todavía.</Empty>}
      {data && data.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <table className="table-base">
            <thead>
              <tr>
                <th>#</th>
                <th>Jugada el</th>
                <th>Fechas de juego</th>
                <th>Saves</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((s, i) => (
                <tr key={s.id}>
                  <td className="muted tabular-nums">{data.length - i}</td>
                  <td>
                    <Link to={String(s.id)} className="font-medium text-indigo-700 hover:underline dark:text-indigo-400">
                      {s.played_on || `Sesión ${s.id}`}
                    </Link>
                  </td>
                  <td>{s.first_date ? `${s.first_date} → ${s.last_date}` : "–"}</td>
                  <td>
                    <span className="flex gap-1">
                      {Object.entries(s.saves_by_status).map(([st, n]) => (
                        <StatusBadge key={st} status={st} count={n} />
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** New session form; with `sessionId` it only adds saves to that session. */
export function UploadForm({ campaignId, sessionId }: { campaignId: number; sessionId?: number }) {
  const [progress, setProgress] = useState(0);
  const upload = useUpload(campaignId, setProgress);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [playedOn, setPlayedOn] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [results, setResults] = useState<UploadResult[] | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setProgress(0);
    setResults(null);
    upload.mutate(
      { files, sessionId, name: name.trim(), played_on: playedOn, notes: notes.trim() },
      {
        onSuccess: (r) => {
          setResults(r.saves);
          setFiles([]);
          setName("");
          setNotes("");
        },
      },
    );
  };

  return (
    <form onSubmit={submit} className="card mb-4 space-y-3">
      {sessionId === undefined && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="s-name">Nombre</label>
            <input id="s-name" className="input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Opcional" />
          </div>
          <div>
            <label className="label" htmlFor="s-date">Jugada el</label>
            <input id="s-date" type="date" className="input w-full" value={playedOn} onChange={(e) => setPlayedOn(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="s-notes">Notas</label>
            <input id="s-notes" className="input w-full" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Opcional" />
          </div>
        </div>
      )}
      <FileDropzone files={files} onChange={setFiles} />
      <div className="flex items-center gap-3">
        <button className="btn btn-primary" disabled={!files.length || upload.isPending}>
          {upload.isPending ? "Subiendo…" : sessionId === undefined ? "Crear sesión" : "Añadir saves"}
        </button>
        {upload.isPending && (
          <div className="h-2 flex-1 overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
            <div className="h-full bg-indigo-600 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
      </div>
      <ErrorBox error={upload.error} />
      {results && (
        <div className="text-sm">
          <p className="mb-1 muted">
            Subida completada. Los saves se procesan en segundo plano; el estado se actualiza solo.
            {results[0] && sessionId === undefined && (
              <> <Link to={`/c/${campaignId}/sessions/${results[0].session_id}`} className="text-indigo-600 hover:underline">Ver sesión</Link></>
            )}
          </p>
          {/* Live status is shown in the saves table; only duplicates need a note, as they are not added here. */}
          <ul className="space-y-0.5">
            {results.filter((r) => r.status === "duplicate").map((r) => (
              <li key={`${r.id}-${r.file}`} className="flex items-center gap-2">
                <StatusBadge status={r.status} />
                <span>{r.file}</span>
                <span className="text-xs muted">ya estaba en la sesión {r.session_id}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </form>
  );
}
