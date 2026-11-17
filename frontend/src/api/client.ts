/**
 * Thin fetch wrapper around the backend, reached through the /api proxy (Vite in dev, nginx in prod).
 * In the read-only build, GETs are served from static JSON files instead (see `staticPath`).
 */
import { READONLY } from "../lib/mode";

export const API_BASE = "/api";
export const STATIC_BASE = "/data";

/**
 * API GET path -> static file exported by backend/tools/export_static.py (keep both in sync):
 * `/campaigns/1/series?metric=gold` -> `/data/campaigns/1/series/gold.json`.
 */
export function staticPath(path: string): string {
  const [route, qs = ""] = path.split("?");
  const metric = new URLSearchParams(qs).get("metric");
  const m = route.match(/^\/campaigns\/(\d+)\/(series|history)$/);
  if (m && metric) return `${STATIC_BASE}/campaigns/${m[1]}/${m[2]}/${encodeURIComponent(metric)}.json`;
  return `${STATIC_BASE}${route}.json`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI errors are {detail: string} or, for validation errors, {detail: [{msg, loc}, ...]}. */
export function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d as { msg?: string }).msg ?? JSON.stringify(d)).join("; ");
  }
  return fallback;
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
  return body as T;
}

export function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (READONLY && init.method && init.method !== "GET") throw new ApiError(405, "Versión de solo lectura");
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return parse<T>(await fetch(API_BASE + path, { ...init, headers }));
}

async function getStatic<T>(path: string): Promise<T> {
  const res = await fetch(staticPath(path));
  // Pages answers missing files with the SPA's index.html, so check the content type too.
  if (!res.ok || !res.headers.get("content-type")?.includes("json")) throw new ApiError(404, "Datos no publicados");
  return (await res.json()) as T;
}

export const get = <T>(path: string) => (READONLY ? getStatic<T>(path) : api<T>(path));
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = (path: string) => api<void>(path, { method: "DELETE" });

/** Multipart upload with progress (fetch has no upload progress events). */
export function upload<T>(path: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  if (READONLY) return Promise.reject(new ApiError(405, "Versión de solo lectura"));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API_BASE + path);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "Error de red"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        /* non-JSON error page from the proxy */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, errorMessage(body, `${xhr.status} ${xhr.statusText}`)));
    };
    xhr.send(form);
  });
}
