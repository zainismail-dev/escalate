/** Browser client for the Escalate API. The API allows only this app's origin (CORS). */
import type {
  CaseDetail,
  CaseSummary,
  Checklist,
  Country,
  Evidence,
  Message,
  Preview,
  ReplyOut,
  Review,
  RunOut,
  Settings,
  TimelineEvent,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type ApiErrorKind = "offline_api" | "model_offline" | "fact_check" | "rate_limited" | "other";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public body: Record<string, unknown> = {},
  ) {
    super(detail);
  }

  /** 503 from the API means the AI model (or PDF renderer) is not reachable: nothing was sent. */
  get kind(): ApiErrorKind {
    if (this.status === 0) return "offline_api";
    if (this.status === 503 && !/pdf|pango|weasy/i.test(this.detail)) return "model_offline";
    if (this.status === 422 && Array.isArray(this.body.issues)) return "fact_check";
    if (this.status === 429) return "rate_limited";
    return "other";
  }

  get issues(): string[] {
    return Array.isArray(this.body.issues) ? (this.body.issues as string[]) : [];
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: body instanceof FormData || body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Cannot reach the Escalate API at ${API_URL}`);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    throw new ApiError(res.status, detail, data);
  }
  return data as T;
}

export const api = {
  health: () => request<{ ok: boolean; version: string; is_cloud: boolean; demo_mode: boolean }>("GET", "/health"),
  countries: () => request<Country[]>("GET", "/countries"),
  listCases: (params: { status?: string; country?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return request<CaseSummary[]>("GET", `/cases${qs.size ? `?${qs}` : ""}`);
  },
  getCase: (id: number) => request<CaseDetail>("GET", `/cases/${id}`),
  createCase: (body: { description: string; country?: string; region?: string; language?: string; company?: string }) =>
    request<CaseDetail>("POST", "/cases", body),
  uploadEvidence: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Evidence>("POST", `/cases/${id}/evidence`, form);
  },
  start: (id: number) => request<RunOut>("POST", `/cases/${id}/start`),
  retry: (id: number) => request<RunOut>("POST", `/cases/${id}/retry`),
  answers: (id: number, answers: Record<string, string>) => request<RunOut>("POST", `/cases/${id}/answers`, { answers }),
  ackChecklist: (id: number) => request<RunOut>("POST", `/cases/${id}/checklist/ack`),
  timeline: (id: number) => request<TimelineEvent[]>("GET", `/cases/${id}/timeline`),
  logReply: (id: number, text: string) => request<ReplyOut>("POST", `/cases/${id}/replies`, { text }),
  overrideVerdict: (id: number, verdict: string) => request<RunOut>("POST", `/cases/${id}/verdict`, { verdict }),
  setLetterLanguage: (id: number, language: string) =>
    request<RunOut>("POST", `/cases/${id}/letter-language`, { language }),
  withdraw: (id: number, reason = "") => request<CaseSummary>("POST", `/cases/${id}/withdraw`, { reason }),
  deleteCase: (id: number) => request<void>("DELETE", `/cases/${id}`),
  exportUrl: (id: number) => `${API_URL}/cases/${id}/export.pdf`,
  printableUrl: (messageId: number) => `${API_URL}/messages/${messageId}/printable.pdf`,
  review: (messageId: number) => request<Review>("GET", `/messages/${messageId}/review`),
  preview: (messageId: number, language: string) =>
    request<Preview>("GET", `/messages/${messageId}/preview?language=${encodeURIComponent(language)}`),
  editMessage: (messageId: number, body: string, subject?: string | null) =>
    request<{ message: Message; warnings: string[] }>("PUT", `/messages/${messageId}`, { body, subject }),
  /** The only way the web app approves a message. The API sets approved_at; then it is sent. */
  approve: (messageId: number) => request<RunOut>("POST", `/messages/${messageId}/approve`, {}),
  reject: (messageId: number, reason: string) => request<RunOut>("POST", `/messages/${messageId}/reject`, { reason }),
  confirmDelivery: (messageId: number, evidenceId?: number) =>
    request<RunOut>("POST", `/messages/${messageId}/confirm-delivery`, { evidence_id: evidenceId ?? null }),
  checklist: (country?: string | null) =>
    request<Checklist>("GET", `/checklist${country ? `?country=${encodeURIComponent(country)}` : ""}`),
  settings: () => request<Settings>("GET", "/settings"),
  saveSettings: (body: Partial<Record<string, string | number>>) => request<Settings>("PUT", "/settings", body),
  testModel: () => request<{ ok: boolean; reply?: string; error?: string }>("POST", "/settings/llm-test"),
  deleteAll: () => request<void>("POST", "/privacy/delete-all"),
  seedDemo: () => request<{ case_ids: number[] }>("POST", "/demo/seed"),
};
