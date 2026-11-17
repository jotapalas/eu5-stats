/**
 * Stable series style per country, shared by every view of a campaign.
 *
 * Colour follows the country, not its rank: it is the country's map colour in the game, from its
 * latest save (so it follows tag changes such as HOL -> NEL), unless the campaign overrides it for
 * the current theme in Settings (e.g. white countries drawn black in light mode). Countries without
 * a game colour yet (saves not reprocessed) fall back to the categorical palette by sorted position.
 *
 * Game colours often collide or are hard to tell apart, so countries are walked in sorted tag order
 * and each one is dashed according to how many earlier countries have the same or a similar colour
 * (first solid, second dashed, third dotted, ...). Filtering never restyles the survivors.
 */
import { useSyncExternalStore } from "react";

import type { CountryColors } from "../api/types";

export const PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
export const PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"];

export interface SeriesStyle {
  color: string;
  /** SVG stroke-dasharray, undefined for solid lines. */
  dash?: string;
}

export type ColorScale = (tag: string) => SeriesStyle;

const DASHES = [undefined, "6 3", "2 3", "8 3 2 3"];
const FALLBACK = { light: "#8a8984", dark: "#8f8e88" };

/** Colours closer than this ("redmean" distance, 0-765) count as the same and get a dash. */
export const SIMILAR_DISTANCE = 60;

function rgb(hex: string): [number, number, number] | null {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null;
}

/** Cheap perceptual RGB distance ("redmean"); Infinity when either colour is not #rrggbb. */
export function colorDistance(a: string, b: string): number {
  const x = rgb(a);
  const y = rgb(b);
  if (!x || !y) return Infinity;
  const r = (x[0] + y[0]) / 2;
  const [dr, dg, db] = [x[0] - y[0], x[1] - y[1], x[2] - y[2]];
  return Math.sqrt((2 + r / 256) * dr * dr + 4 * dg * dg + (2 + (255 - r) / 256) * db * db);
}

export function colorScale(
  tags: Iterable<string>,
  dark = false,
  colors: Record<string, CountryColors> = {},
): ColorScale {
  const palette = dark ? PALETTE_DARK : PALETTE_LIGHT;
  const styles = new Map<string, SeriesStyle>();
  const seen: string[] = [];
  [...new Set(tags)].sort().forEach((tag, i) => {
    const c = colors[tag];
    const color = (dark ? c?.dark : c?.light) ?? c?.game ?? palette[i % palette.length];
    const n = seen.filter((other) => colorDistance(color, other) < SIMILAR_DISTANCE).length;
    seen.push(color);
    styles.set(tag, { color, dash: DASHES[n % DASHES.length] });
  });
  return (tag) => styles.get(tag) ?? { color: dark ? FALLBACK.dark : FALLBACK.light, dash: DASHES[2] };
}

// ------------------------------------------------------------------ dark mode
// Light by default regardless of the OS preference; dark is an opt-in remembered per browser.
// index.html applies the stored choice before first paint to avoid a flash.
const THEME_KEY = "eu5stats.theme";
const listeners = new Set<() => void>();

function readStored(): boolean {
  try {
    return localStorage.getItem(THEME_KEY) === "dark";
  } catch {
    return false;
  }
}

let dark = typeof window !== "undefined" && readStored();

function applyTheme(value: boolean) {
  const root = document.documentElement;
  root.classList.toggle("dark", value);
  root.style.colorScheme = value ? "dark" : "light";
}

export function setDarkMode(value: boolean) {
  dark = value;
  try {
    localStorage.setItem(THEME_KEY, value ? "dark" : "light");
  } catch {
    // storage unavailable: the choice just won't survive a reload
  }
  applyTheme(value);
  listeners.forEach((cb) => cb());
}

export function useDarkMode(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => dark,
    () => false,
  );
}

/** Chart chrome colours (axes, grid) per mode: recessive, never competing with the data. */
export const chartChrome = (dark: boolean) =>
  dark ? { axis: "#8f8e88", grid: "#2c2c2a", text: "#c3c2b7" } : { axis: "#8a8984", grid: "#e8e7e3", text: "#52514e" };
