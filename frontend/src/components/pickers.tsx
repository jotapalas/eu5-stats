/** Metric and country selectors. */
import { useRef, useState, type DragEvent } from "react";

import type { MetricDef } from "../api/types";
import { categoryLabel, metricLabel } from "../i18n";
import type { ColorScale } from "../lib/colors";
import { formatValue } from "../lib/format";
import { Swatch } from "./ui-swatch";

export function MetricPicker({ metrics, value, onChange, className = "" }: {
  metrics: MetricDef[];
  value: string;
  onChange: (name: string) => void;
  className?: string;
}) {
  const groups = new Map<string, MetricDef[]>();
  for (const m of metrics) groups.set(m.category, [...(groups.get(m.category) ?? []), m]);
  return (
    <select className={`input ${className}`} value={value} onChange={(e) => onChange(e.target.value)}>
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

/**
 * Country selector that doubles as the chart legend: one row per country with a checkbox,
 * its line style, players and latest value, sorted best first. Hovering a row highlights its line.
 */
export function CountryList({ tags, selected, onChange, color, players, latest, rank, onHover }: {
  tags: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  color: ColorScale;
  players: (tag: string) => string[];
  /** Latest value per country; countries without data go last. */
  latest: Record<string, number | undefined>;
  /** Rank metric: lowest value first. */
  rank: boolean;
  onHover: (tag: string | null) => void;
}) {
  const toggle = (t: string) => {
    const n = new Set(selected);
    if (n.has(t)) n.delete(t);
    else n.add(t);
    onChange(n);
  };
  const played = tags.filter((t) => players(t).length);
  const valid = (v: number | undefined) => v !== undefined && !(rank && v <= 0);
  const sorted = [...tags].sort((a, b) => {
    const va = latest[a], vb = latest[b];
    if (!valid(va) || !valid(vb)) return Number(!valid(va)) - Number(!valid(vb)) || a.localeCompare(b);
    return rank ? va! - vb! : vb! - va!;
  });
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set(tags))}>Todos</button>
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set(played))}>Jugadores</button>
        <button type="button" className="btn btn-sm" onClick={() => onChange(new Set())}>Ninguno</button>
      </div>
      <ul className="max-h-[60vh] space-y-1 overflow-y-auto pr-1" onMouseLeave={() => onHover(null)}>
        {sorted.map((t) => {
          const on = selected.has(t);
          const p = players(t);
          return (
            <li key={t}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => toggle(t)}
                onMouseEnter={() => onHover(on ? t : null)}
                title={p.length ? p.join(", ") : "IA"}
                className={`flex w-full items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-left text-xs ${
                  on
                    ? "border-slate-400 bg-slate-100 font-medium hover:bg-slate-200 dark:border-slate-500 dark:bg-slate-800 dark:hover:bg-slate-700"
                    : "border-slate-200 text-slate-400 hover:border-slate-300 dark:border-slate-800 dark:text-slate-500"
                }`}
              >
                {on && <Swatch style={color(t)} />}
                <span>{t}</span>
                <span className="min-w-0 flex-1 truncate font-normal muted">{p.length ? `· ${p.join(", ")}` : ""}</span>
                <span className="shrink-0 tabular-nums">{valid(latest[t]) ? formatValue(latest[t]) : "–"}</span>
              </button>
            </li>
          );
        })}
      </ul>
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
        <p className="mt-1 text-xs muted">Un save por año de juego; el orden no importa.</p>
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
