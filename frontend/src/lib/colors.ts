/**
 * Stable series style per country, shared by every view of a campaign.
 *
 * Eight validated categorical hues (light and dark steps). Colour follows the country, not its
 * rank: slots are assigned by sorted position among all the campaign's countries, so filtering
 * never repaints the survivors. Campaigns have more than eight countries, so slots 9-16 reuse
 * the hues with a dashed stroke (composite encoding) and the rest fall back to grey dotted.
 */
import { useSyncExternalStore } from "react";

export const PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
export const PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"];
const OVERFLOW = { light: "#8a8984", dark: "#8f8e88" };

export interface SeriesStyle {
  color: string;
  /** SVG stroke-dasharray, undefined for solid lines. */
  dash?: string;
}

export type ColorScale = (tag: string) => SeriesStyle;

const DASHES = [undefined, "6 3", "2 3"];

export function colorScale(tags: Iterable<string>, dark = false): ColorScale {
  const palette = dark ? PALETTE_DARK : PALETTE_LIGHT;
  const index = new Map([...new Set(tags)].sort().map((t, i) => [t, i]));
  return (tag) => {
    const i = index.get(tag);
    if (i === undefined || i >= palette.length * 2) return { color: dark ? OVERFLOW.dark : OVERFLOW.light, dash: DASHES[2] };
    return { color: palette[i % palette.length], dash: DASHES[Math.floor(i / palette.length)] };
  };
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
