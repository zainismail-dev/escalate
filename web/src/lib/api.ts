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

/** Every state-changing request carries this header; the API refuses those without it (CSRF). */
const CSRF_HEADER = { "X-Escalate-Request": "1" };

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  const headers: Record<string, string> = method === "GET" ? {} : { ...CSRF_HEADER };
  if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
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
  health: () => request<{ ok: boolean }>("GET", "/health"),
  countries: () => request<Country[]>("GET", "/countries"),
  listCases: (params: { status?: string; country?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return request<CaseSummary[]>("GET", `/cases${qs.size ? `?${qs}` : ""}`);
  },
  getCase: (id: string) => request<CaseDetail>("GET", `/cases/${id}`),
  renameCase: (id: string, title: string) => request<CaseDetail>("PATCH", `/cases/${id}`, { title }),
  createCase: (body: { description: string; country?: string; region?: string; language?: string; company?: string }) =>
    request<CaseDetail>("POST", "/cases", body),
  uploadEvidence: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Evidence>("POST", `/cases/${id}/evidence`, form);
  },
  start: (id: string) => request<RunOut>("POST", `/cases/${id}/start`),
  retry: (id: string) => request<RunOut>("POST", `/cases/${id}/retry`),
  answers: (id: string, answers: Record<string, string>) => request<RunOut>("POST", `/cases/${id}/answers`, { answers }),
  ackChecklist: (id: string) => request<RunOut>("POST", `/cases/${id}/checklist/ack`),
  timeline: (id: string) => request<TimelineEvent[]>("GET", `/cases/${id}/timeline`),
  logReply: (id: string, text: string) => request<ReplyOut>("POST", `/cases/${id}/replies`, { text }),
  overrideVerdict: (id: string, verdict: string) => request<RunOut>("POST", `/cases/${id}/verdict`, { verdict }),
  setLetterLanguage: (id: string, language: string) =>
    request<RunOut>("POST", `/cases/${id}/letter-language`, { language }),
  withdraw: (id: string, reason = "") => request<CaseSummary>("POST", `/cases/${id}/withdraw`, { reason }),
  deleteCase: (id: string) => request<void>("DELETE", `/cases/${id}`),
  exportUrl: (id: string) => `${API_URL}/cases/${id}/export.pdf`,
  printableUrl: (messageId: string) => `${API_URL}/messages/${messageId}/printable.pdf`,
  review: (messageId: string) => request<Review>("GET", `/messages/${messageId}/review`),
  preview: (messageId: string, language: string) =>
    request<Preview>("GET", `/messages/${messageId}/preview?language=${encodeURIComponent(language)}`),
  editMessage: (messageId: string, body: string, subject?: string | null) =>
    request<{ message: Message; warnings: string[] }>("PUT", `/messages/${messageId}`, { body, subject }),
  /**
   * The only way the web app approves a message. The user must state the exact recipient they
   * checked; the API sets approved_at, then it is sent.
   */
  approve: (messageId: string, recipient: string | null) =>
    request<RunOut>("POST", `/messages/${messageId}/approve`, { confirm: true, recipient }),
  setRecipient: (messageId: string, recipient: string) =>
    request<Message>("POST", `/messages/${messageId}/recipient`, { recipient }),
  confirmResolution: (caseId: string, resolved: boolean, verdict?: string) =>
    request<RunOut>("POST", `/cases/${caseId}/resolution`, { resolved, verdict: verdict ?? null }),
  reject: (messageId: string, reason: string) => request<RunOut>("POST", `/messages/${messageId}/reject`, { reason }),
  confirmDelivery: (messageId: string, evidenceId?: number) =>
    request<RunOut>("POST", `/messages/${messageId}/confirm-delivery`, { evidence_id: evidenceId ?? null }),
  checklist: (country?: string | null) =>
    request<Checklist>("GET", `/checklist${country ? `?country=${encodeURIComponent(country)}` : ""}`),
  settings: () => request<Settings>("GET", "/settings"),
  saveSettings: (body: Partial<Record<string, string | number>>) => request<Settings>("PUT", "/settings", body),
  testModel: () => request<{ ok: boolean; reply?: string; error?: string }>("POST", "/settings/llm-test"),
  deleteAll: () => request<void>("POST", "/privacy/delete-all", { confirm: true }),
  seedDemo: () => request<{ case_ids: string[] }>("POST", "/demo/seed"),
};
