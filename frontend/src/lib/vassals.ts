/**
 * "Incluir vasallos" selector: some metrics are also stored as country + vassals (direct vassals or every
 * level) under other names, listed in /metrics `vassal_metrics`. The scope lives in the `vassals` URL param.
 */
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

import type { MetricsResponse } from "../api/types";

export type VassalScope = "none" | "direct" | "all";
export const VASSAL_SCOPES: VassalScope[] = ["none", "direct", "all"];

export const VASSALS_PARAM = "vassals";

export function parseScope(param: string | null): VassalScope {
  return param === "direct" || param === "all" ? param : "none";
}

type VassalMetrics = MetricsResponse["vassal_metrics"] | undefined;

export function hasVassalVariant(vm: VassalMetrics, name: string): boolean {
  return !!vm?.[name];
}

/** Scope from the URL plus a setter that keeps the other params (absent = "none"). */
export function useVassalScope(): [VassalScope, (s: VassalScope) => void] {
  const [params, setParams] = useSearchParams();
  const set = useCallback(
    (s: VassalScope) =>
      setParams((p) => {
        const n = new URLSearchParams(p);
        if (s === "none") n.delete(VASSALS_PARAM);
        else n.set(VASSALS_PARAM, s);
        return n;
      }, { replace: true }),
    [setParams],
  );
  return [parseScope(params.get(VASSALS_PARAM)), set];
}

/** `&vassals=...` (or `?vassals=...`) to propagate the scope in links ("" for "none"). */
export const scopeQuery = (s: VassalScope, sep: "&" | "?" = "&") => (s === "none" ? "" : `${sep}${VASSALS_PARAM}=${s}`);

/** Stored metric name to read for `name` with the given scope (the base name if it has no variant). */
export function resolveMetric(vm: VassalMetrics, name: string, scope: VassalScope): string {
  return scope === "none" ? name : vm?.[name]?.[scope] ?? name;
}
