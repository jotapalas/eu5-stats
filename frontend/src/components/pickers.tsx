/** Metric and country selectors. */
import { useRef, useState, type DragEvent } from "react";

import type { MetricDef } from "../api/types";
import { categoryLabel, metricLabel } from "../i18n";
import type { ColorScale } from "../lib/colors";
import { Swatch } from "./ui-swatch";

export function MetricPicker({ metrics, value, onChange }: {
  metrics: MetricDef[];
  value: string;
  onChange: (name: string) => void;
}) {
  const groups = new Map<string, MetricDef[]>();
  for (const m of metrics) groups.set(m.category, [...(groups.get(m.category) ?? []), m]);
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      {[...groups].map(([cat, ms]) => (
        <optgroup key={cat} label={categoryLabel(cat)}>
          {ms.map((m) => (
            <option key={m.name} value={m.name} title={m.description}>
              {metricLabel(m.name, m.description)}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

export function CountryMultiSelect({ tags, selected, onChange, color, players }: {
  tags: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  color: ColorScale;
  players: (tag: string) => string[];
}) {
  const toggle = (t: string) => {
    const n = new Set(selected);
    if (n.has(t)) n.delete(t);
    else n.add(t);
    onChange(n);
  };
  const played = tags.filter((t) => players(t).length);
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5 text-xs">
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set(tags))}>Todos</button>
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set(played))}>Jugadores</button>
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set())}>Ninguno</button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => {
          const on = selected.has(t);
          const p = players(t);
          return (
            <button
              key={t}
              type="button"
              onClick={() => toggle(t)}
              title={p.length ? p.join(", ") : "IA"}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
                on
                  ? "border-slate-400 bg-slate-100 font-medium dark:border-slate-500 dark:bg-slate-800"
                  : "border-slate-200 text-slate-400 dark:border-slate-800 dark:text-slate-500"
              }`}
            >
              {on && <Swatch style={color(t)} />}
              {t}
              {p.length > 0 && <span className="muted">· {p.join(", ")}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const MB = 1024 * 1024;

export function FileDropzone({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const add = (list: FileList | null) => {
    if (!list) return;
    const names = new Set(files.map((f) => f.name));
    onChange([...files, ...[...list].filter((f) => !names.has(f.name))].sort((a, b) => a.name.localeCompare(b.name)));
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    add(e.dataTransfer.files);
  };
  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        onClick={() => input.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center text-sm ${
          over ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" : "border-slate-300 dark:border-slate-700"
        }`}
      >
        <p className="font-medium">Arrastra aquí los saves (.eu5) o haz clic para elegirlas</p>
        <p className="mt-1 text-xs muted">Una partida por año de juego; el orden no importa.</p>
        <input
          ref={input}
          type="file"
          accept=".eu5"
          multiple
          hidden
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {files.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {files.map((f) => (
            <li key={f.name} className="flex items-center justify-between gap-2">
              <span className="truncate">{f.name}</span>
              <span className="flex items-center gap-2">
                <span className="text-xs muted tabular-nums">{(f.size / MB).toFixed(1)} MB</span>
                <button type="button" className="btn btn-sm" onClick={() => onChange(files.filter((x) => x !== f))}>
                  Quitar
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
