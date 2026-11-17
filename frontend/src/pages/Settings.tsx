/** Campaign settings: tracked countries, rename and delete. */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import {
  useAddCountry,
  useCountries,
  useDeleteCampaign,
  useRemoveCountry,
  useReprocessCampaign,
  useUpdateCampaign,
  useUpdateCountry,
  type CountryPatch,
} from "../api/hooks";
import type { TrackedCountry } from "../api/types";
import { ErrorBox, PageTitle, Spinner } from "../components/ui";
import { Swatch } from "../components/ui-swatch";
import { useCampaignCtx } from "./CampaignLayout";

export function Settings() {
  return (
    <div className="space-y-5">
      <TrackedCountries />
      <Reprocess />
      <EditCampaign />
    </div>
  );
}

/** Re-extract every save of the campaign (after changing tracked countries or new metrics). */
function Reprocess() {
  const { id, campaign } = useCampaignCtx();
  const reprocess = useReprocessCampaign(id);
  const run = () => {
    if (confirm("¿Reprocesar todos los saves de la campaña? Puede tardar varios minutos.")) reprocess.mutate();
  };
  return (
    <section className="card">
      <PageTitle>Reprocesar</PageTitle>
      <p className="mb-3 text-sm muted">
        Vuelve a extraer las estadísticas de todos los saves ya subidos con la lista de países seguidos y las métricas
        actuales. Úsalo tras añadir o quitar países o tras actualizar la aplicación. Los saves se procesan de uno en uno
        en segundo plano.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" onClick={run} disabled={reprocess.isPending || campaign.sessions === 0}>
          Reprocesar todos los saves
        </button>
        {reprocess.data && <span className="text-sm muted">{reprocess.data.queued} saves en cola.</span>}
      </div>
      <ErrorBox error={reprocess.error} />
    </section>
  );
}

function TrackedCountries() {
  const { id } = useCampaignCtx();
  const { data, error, isLoading } = useCountries(id);
  const add = useAddCountry(id);
  const remove = useRemoveCountry(id);
  const update = useUpdateCountry(id);
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
      <p className="mb-3 text-sm muted">
        «Jugador principal» es el nombre que aparece en el ranking, la comparativa y la ficha de país. Si lo dejas vacío
        se usa el del último save. Las sesiones siempre muestran el jugador que indica cada save.
      </p>
      <p className="mb-3 text-sm muted">
        «Color» es el del país en el juego según el último save. Si un color no se ve bien en las gráficas, cámbialo para
        el modo claro, el oscuro o ambos (× vuelve al del juego). Los países con colores iguales o parecidos se dibujan con
        línea discontinua.
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
      <ErrorBox error={add.error ?? remove.error ?? update.error ?? error} />
      {isLoading && <Spinner />}
      {data && (
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Añadido como</th>
                <th>Tags</th>
                <th>Jugador principal</th>
                <th>Color</th>
                <th>Jugadores en los saves</th>
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
                  <td>{c.tags.join(" - ") || "–"}</td>
                  <td>
                    <PlayerInput country={c} onSave={(player) => update.mutate({ tag: c.tag, player })} />
                  </td>
                  <td>
                    <ColorEditor country={c} onSave={(patch) => update.mutate({ tag: c.tag, ...patch })} />
                  </td>
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

/** Inline editor: saves on Enter or blur when changed; suggests the names seen in the saves. */
function PlayerInput({ country, onSave }: { country: TrackedCountry; onSave: (player: string | null) => void }) {
  const [value, setValue] = useState(country.player ?? "");
  const listId = `players-${country.added_as}-${country.country_id}`;
  const commit = () => {
    const next = value.trim() || null;
    if (next !== country.player) onSave(next);
  };
  return (
    <>
      <input
        className="input w-40 py-1"
        value={value}
        placeholder={country.players[country.players.length - 1] ?? "IA"}
        list={listId}
        maxLength={100}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        aria-label={`Jugador principal de ${country.tag}`}
      />
      <datalist id={listId}>
        {country.players.map((p) => (
          <option key={p} value={p} />
        ))}
      </datalist>
    </>
  );
}

type ColorField = "color_light" | "color_dark";
const COLOR_FIELDS: { field: ColorField; label: string }[] = [
  { field: "color_light", label: "Claro" },
  { field: "color_dark", label: "Oscuro" },
];

/** Game colour swatch plus a colour picker per theme; a reset (×) drops the override. */
function ColorEditor({ country, onSave }: { country: TrackedCountry; onSave: (patch: CountryPatch) => void }) {
  const { color } = useCampaignCtx();
  return (
    <div className="flex items-center gap-3">
      {/* What the charts draw now (current theme, dashed if it clashes with another country). */}
      {country.active && <Swatch style={color(country.tag)} />}
      {COLOR_FIELDS.map(({ field, label }) => (
        <ColorInput
          key={field}
          label={label}
          tag={country.tag}
          saved={country[field]}
          fallback={country.color}
          onSave={(value) => onSave({ [field]: value })}
        />
      ))}
    </div>
  );
}

function ColorInput(props: {
  label: string;
  tag: string;
  saved: string | null;
  fallback: string | null;
  onSave: (value: string | null) => void;
}) {
  const { label, tag, saved, fallback, onSave } = props;
  const [value, setValue] = useState(saved ?? fallback ?? "#888888");
  const [dirty, setDirty] = useState(false);
  const save = useRef(onSave);
  save.current = onSave;
  useEffect(() => {
    if (!dirty) setValue(saved ?? fallback ?? "#888888");
  }, [saved, fallback, dirty]);
  // The picker fires on every drag step: save once it settles.
  useEffect(() => {
    if (!dirty) return;
    const t = setTimeout(() => {
      setDirty(false);
      if (value !== saved) save.current(value);
    }, 400);
    return () => clearTimeout(t);
  }, [dirty, value, saved]);
  return (
    <label className="flex items-center gap-1 text-xs muted" title={saved ? "Color propio" : "Color del juego"}>
      {label}
      <input
        type="color"
        className={`h-6 w-8 cursor-pointer rounded border bg-transparent p-0 ${
          saved ? "border-indigo-500" : "border-slate-300 dark:border-slate-700"
        }`}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setDirty(true);
        }}
        aria-label={`Color de ${tag} en modo ${label.toLowerCase()}`}
      />
      {saved && (
        <button
          type="button"
          className="px-1 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          onClick={() => onSave(null)}
          aria-label={`Usar el color del juego para ${tag} en modo ${label.toLowerCase()}`}
        >
          ×
        </button>
      )}
    </label>
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
