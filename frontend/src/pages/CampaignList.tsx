import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useCampaigns, useCreateCampaign } from "../api/hooks";
import { Empty, ErrorBox, PageTitle, Spinner, StatusBadge } from "../components/ui";

export function CampaignList() {
  const { data, error, isLoading } = useCampaigns();
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <PageTitle actions={<button className="btn btn-primary" onClick={() => setCreating((v) => !v)}>Nueva campaña</button>}>
        Campañas
      </PageTitle>
      {creating && <CreateCampaign onDone={() => setCreating(false)} />}
      {isLoading && <Spinner />}
      <ErrorBox error={error} />
      {data && data.length === 0 && <Empty>Todavía no hay campañas. Crea una para empezar a subir saves.</Empty>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((c) => (
          <Link key={c.id} to={`/c/${c.id}`} className="card block transition hover:border-indigo-400">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold">{c.name}</h3>
              <span className="flex gap-1">
                {c.saves_pending > 0 && <StatusBadge status="processing" count={c.saves_pending} />}
                {c.saves_error > 0 && <StatusBadge status="error" count={c.saves_error} />}
              </span>
            </div>
            {c.description && <p className="mt-1 line-clamp-2 text-sm muted">{c.description}</p>}
            <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <Stat label="Fechas" value={c.first_date ? `${c.first_date.split(".")[0]}–${c.last_date?.split(".")[0]}` : "–"} />
              <Stat label="Sesiones" value={c.sessions} />
              <Stat label="Países" value={c.countries.length} />
            </dl>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="muted">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function CreateCampaign({ onDone }: { onDone: () => void }) {
  const create = useCreateCampaign();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), description: description.trim() || null },
      {
        onSuccess: (c) => {
          onDone();
          navigate(`/c/${c.id}/sessions`);
        },
      },
    );
  };
  return (
    <form onSubmit={submit} className="card mb-4 grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
      <div>
        <label className="label" htmlFor="c-name">Nombre</label>
        <input id="c-name" className="input w-full" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} autoFocus />
      </div>
      <div>
        <label className="label" htmlFor="c-desc">Descripción</label>
        <input id="c-desc" className="input w-full" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <button className="btn btn-primary" disabled={!name.trim() || create.isPending}>Crear</button>
      <div className="sm:col-span-3"><ErrorBox error={create.error} /></div>
    </form>
  );
}
