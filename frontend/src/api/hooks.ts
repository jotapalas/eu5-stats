/**
 * TanStack Query hooks. Every campaign-scoped key starts with ["campaign", id] so a single
 * invalidation refreshes all views of a campaign (e.g. when the worker finishes a save).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, patch, post, query, upload } from "./client";
import type {
  Campaign,
  CampaignDetail,
  CountryTimeline,
  HistoryResponse,
  MetricsResponse,
  SeriesResponse,
  Session,
  SessionDetail,
  SessionSummary,
  TrackedCountry,
  UploadResponse,
} from "./types";

const POLL_MS = 2000;

export const keys = {
  campaigns: ["campaigns"] as const,
  metrics: ["metrics"] as const,
  campaign: (id: number) => ["campaign", id] as const,
  series: (id: number, metric: string) => ["campaign", id, "series", metric] as const,
  history: (id: number, metric: string) => ["campaign", id, "history", metric] as const,
  country: (id: number, tag: string) => ["campaign", id, "country", tag] as const,
  countries: (id: number) => ["campaign", id, "countries"] as const,
  sessions: (id: number) => ["campaign", id, "sessions"] as const,
  session: (id: number, sid: number) => ["campaign", id, "session", sid] as const,
  summary: (id: number, sid: number) => ["campaign", id, "session", sid, "summary"] as const,
};

// ------------------------------------------------------------------ queries
export const useCampaigns = () => useQuery({ queryKey: keys.campaigns, queryFn: () => get<Campaign[]>("/campaigns") });

export const useMetrics = () =>
  useQuery({ queryKey: keys.metrics, queryFn: () => get<MetricsResponse>("/metrics"), staleTime: Infinity });

/** Polls while saves are pending/processing. */
export const useCampaign = (id: number) =>
  useQuery({
    queryKey: keys.campaign(id),
    queryFn: () => get<CampaignDetail>(`/campaigns/${id}`),
    refetchInterval: (q) => (q.state.data?.saves_pending ? POLL_MS : false),
  });

export const useSeries = (id: number, metric: string, enabled = true) =>
  useQuery({
    queryKey: keys.series(id, metric),
    queryFn: () => get<SeriesResponse>(`/campaigns/${id}/series${query({ metric })}`),
    enabled: enabled && !!metric,
  });

export const useHistory = (id: number, metric: string, enabled = true) =>
  useQuery({
    queryKey: keys.history(id, metric),
    queryFn: () => get<HistoryResponse>(`/campaigns/${id}/history${query({ metric })}`),
    enabled: enabled && !!metric,
  });

export const useCountry = (id: number, tag: string) =>
  useQuery({
    queryKey: keys.country(id, tag),
    queryFn: () => get<CountryTimeline>(`/campaigns/${id}/countries/${encodeURIComponent(tag)}`),
  });

export const useCountries = (id: number) =>
  useQuery({ queryKey: keys.countries(id), queryFn: () => get<TrackedCountry[]>(`/campaigns/${id}/countries`) });

const anyPending = (s: Session) => !!(s.saves_by_status.pending || s.saves_by_status.processing);

export const useSessions = (id: number) =>
  useQuery({
    queryKey: keys.sessions(id),
    queryFn: () => get<Session[]>(`/campaigns/${id}/sessions`),
    refetchInterval: (q) => (q.state.data?.some(anyPending) ? POLL_MS : false),
  });

export const useSession = (id: number, sid: number) =>
  useQuery({
    queryKey: keys.session(id, sid),
    queryFn: () => get<SessionDetail>(`/sessions/${sid}`),
    refetchInterval: (q) => (q.state.data && anyPending(q.state.data) ? POLL_MS : false),
  });

export const useSessionSummary = (id: number, sid: number) =>
  useQuery({ queryKey: keys.summary(id, sid), queryFn: () => get<SessionSummary>(`/sessions/${sid}/summary`) });

// ------------------------------------------------------------------ mutations
function useInvalidate() {
  const qc = useQueryClient();
  return (key: readonly unknown[]) => qc.invalidateQueries({ queryKey: key });
}

export function useCreateCampaign() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { name: string; description?: string | null }) => post<Campaign>("/campaigns", body),
    onSuccess: () => invalidate(keys.campaigns),
  });
}

export function useUpdateCampaign(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string | null }) => patch<Campaign>(`/campaigns/${id}`, body),
    onSuccess: () => Promise.all([invalidate(keys.campaigns), invalidate(keys.campaign(id))]),
  });
}

export function useDeleteCampaign(id: number) {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: () => del(`/campaigns/${id}`), onSuccess: () => invalidate(keys.campaigns) });
}

export function useReprocessCampaign(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<{ queued: number }>(`/campaigns/${id}/reprocess`),
    onSuccess: () => invalidate(keys.campaign(id)),
  });
}

export function useAddCountry(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (tag: string) => post<TrackedCountry>(`/campaigns/${id}/countries`, { tag }),
    onSuccess: () => invalidate(keys.campaign(id)),
  });
}

export function useRemoveCountry(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (tag: string) => del(`/campaigns/${id}/countries/${encodeURIComponent(tag)}`),
    onSuccess: () => invalidate(keys.campaign(id)),
  });
}

/** Main player shown campaign-wide for a country; null/empty goes back to the saves' players. */
export function useSetCountryPlayer(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ tag, player }: { tag: string; player: string | null }) =>
      patch<TrackedCountry>(`/campaigns/${id}/countries/${encodeURIComponent(tag)}`, { player }),
    onSuccess: () => invalidate(keys.campaign(id)),
  });
}

export interface NewSession {
  files: File[];
  name?: string;
  played_on?: string;
  notes?: string;
}

/** Creates a session with its saves, or adds saves to an existing one when `sessionId` is given. */
export function useUpload(id: number, onProgress?: (fraction: number) => void) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ sessionId, ...s }: NewSession & { sessionId?: number }) => {
      const form = new FormData();
      for (const f of s.files) form.append("files", f, f.name);
      if (sessionId !== undefined) return upload<UploadResponse>(`/sessions/${sessionId}/saves`, form, onProgress);
      if (s.name) form.append("name", s.name);
      if (s.played_on) form.append("played_on", s.played_on);
      if (s.notes) form.append("notes", s.notes);
      return upload<UploadResponse>(`/campaigns/${id}/sessions`, form, onProgress);
    },
    onSuccess: () => Promise.all([invalidate(keys.campaign(id)), invalidate(keys.campaigns)]),
  });
}

export function useDeleteSession(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (sid: number) => del(`/sessions/${sid}`),
    onSuccess: () => Promise.all([invalidate(keys.campaign(id)), invalidate(keys.campaigns)]),
  });
}

export function useReprocessSave(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (saveId: number) => post<{ queued: number }>(`/saves/${saveId}/reprocess`),
    onSuccess: () => invalidate(keys.campaign(id)),
  });
}
