/** Number and game-date formatting. */

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const MONTH_START = MONTH_DAYS.map((_, i) => MONTH_DAYS.slice(0, i).reduce((a, b) => a + b, 0));

/**
 * Game date "Y.M.D" -> fractional year, so saves are spaced proportionally on a time axis.
 * The game uses 365-day years without leap days (see backend/app/eu5/values.py).
 */
export function gameDateToYear(date: string): number {
  const [y, m = 1, d = 1] = date.split(".").map(Number);
  return y + (MONTH_START[m - 1] + d - 1) / 365;
}

const compact = new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 1 });
const small = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });

/** Compact for big numbers (12,3 mil), up to 2 decimals for small ones (stability, inflation). */
export function formatValue(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 10_000) return compact.format(v);
  if (a >= 100) return integer.format(v);
  return small.format(v);
}

export function formatDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return (v > 0 ? "+" : "") + formatValue(v);
}

/** Metrics where a lower value is better (used to colour deltas and default sort order). */
export const LOWER_IS_BETTER = new Set(["score_place", "great_power_rank", "inflation", "war_exhaustion"]);

/** Rank metrics (1 = best): charted on a reversed log axis so the leader is on top. */
export const RANK_METRICS = new Set(["score_place", "great_power_rank"]);

export function deltaTone(metric: string, delta: number | null | undefined): "good" | "bad" | "neutral" {
  if (!delta) return "neutral";
  const up = delta > 0;
  return up !== LOWER_IS_BETTER.has(metric) ? "good" : "bad";
}

/** "ENG (Miranda, Bob)" or just "ENG" for AI countries. */
export function countryLabel(tag: string, players?: string[]): string {
  return players && players.length ? `${tag} (${players.join(", ")})` : tag;
}
