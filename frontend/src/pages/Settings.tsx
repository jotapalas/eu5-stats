/** Campaign settings: tracked countries, rename and delete. */
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import {
  useAddCountry,
  useCountries,
  useDeleteCampaign,
  useRemoveCountry,
  useUpdateCampaign,
} from "../api/hooks";
import { ErrorBox, PageTitle, Spinner } from "../components/ui";
import { useCampaignCtx } from "./CampaignLayout";

export function Settings() {
  return (
    <div className="space-y-5">
      <TrackedCountries />
      <EditCampaign />
    </div>
  );
}

function TrackedCountries() {
  const { id } = useCampaignCtx();
  const { data, error, isLoading } = useCountries(id);
  const add = useAddCountry(id);
  const remove = useRemoveCountry(id);
  const [tag, setTag] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(tag.trim().toUpperCase(), { onSuccess: () => setTag("") });
  };

  return (
    <section className="card">
      <PageTitle>Países seguidos</PageTitle>
      <p className="mb-3 text-sm muted">
        Los países de los jugadores se añaden solos. Añade aquí países de la IA que quieras seguir; los cambios se aplican
        a los saves que se procesen a partir de ahora (usa «Reprocesar» para las ya subidas). Quitar un país conserva sus datos.
      </p>
      <form onSubmit={submit} className="mb-3 flex gap-2">
        <input
          className="input w-32 uppercase"
          placeholder="TAG"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          maxLength={8}
          pattern="[A-Za-z0-9_]+"
        />
        <button className="btn btn-primary" disabled={!tag.trim() || add.isPending}>Añadir</button>
      </form>
      <ErrorBox error={add.error ?? remove.error ?? error} />
      {isLoading && <Spinner />}
      {data && (
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Añadido como</th>
                <th>Tags</th>
                <th>Jugadores</th>
                <th className="num">Saves</th>
                <th>Último dato</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={`${c.added_as}-${c.country_id}`} className={c.active ? "" : "opacity-50"}>
                  <td className="font-medium">{c.tag}</td>
                  <td>{c.added_as}</td>
                  <td>{c.tags.join(" → ") || "–"}</td>
                  <td>{c.players.join(", ") || "IA"}</td>
                  <td className="num">{c.snapshots}</td>
                  <td>{c.last_date ?? (c.country_id === null ? "pendiente de resolver" : "–")}</td>
                  <td className="text-right">
                    {c.active ? (
                      <button className="btn btn-sm" onClick={() => remove.mutate(c.tag)}>Quitar</button>
                    ) : (
                      <button className="btn btn-sm" onClick={() => add.mutate(c.tag)}>Reactivar</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EditCampaign() {
  const { id, campaign } = useCampaignCtx();
  const update = useUpdateCampaign(id);
  const del = useDeleteCampaign(id);
  const navigate = useNavigate();
  const [name, setName] = useState(campaign.name);
  const [description, setDescription] = useState(campaign.description ?? "");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    update.mutate({ name: name.trim(), description: description.trim() });
  };
  const remove = () => {
    if (confirm(`¿Borrar la campaña «${campaign.name}»?`)) del.mutate(undefined, { onSuccess: () => navigate("/") });
  };

  return (
    <section className="card">
      <PageTitle>Campaña</PageTitle>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
        <div>
          <label className="label" htmlFor="e-name">Nombre</label>
          <input id="e-name" className="input w-full" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
        </div>
        <div>
          <label className="label" htmlFor="e-desc">Descripción</label>
          <input id="e-desc" className="input w-full" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <button className="btn btn-primary" disabled={update.isPending || !name.trim()}>Guardar</button>
      </form>
      <ErrorBox error={update.error} />
      <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
        <button className="btn btn-danger" onClick={remove} disabled={del.isPending || campaign.sessions > 0}>
          Borrar campaña
        </button>
        {campaign.sessions > 0 && <span className="ml-3 text-xs muted">Borra antes sus {campaign.sessions} sesiones.</span>}
        <ErrorBox error={del.error} />
      </div>
    </section>
  );
}
