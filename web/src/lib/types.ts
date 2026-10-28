/** Shapes returned by the Escalate API (escalate/api/schemas.py). */

export type CaseStatus =
  | "intake"
  | "urgent_checklist"
  | "drafting"
  | "awaiting_approval"
  | "waiting_reply"
  | "pick_next"
  | "resolved"
  | "closed_unresolved"
  | "withdrawn";

export type WaitingFor =
  | "questions"
  | "urgent_checklist"
  | "approve_draft"
  | "confirm_delivery"
  | "waiting_reply"
  | null;

export interface Fact {
  key: string;
  value: string;
  display?: string | null;
  confidence: number;
  source_evidence_id: number | null;
}

export interface Evidence {
  id: number;
  kind: string;
  filename: string;
  sha256: string;
  needs_review: boolean;
  ocr_confidence: number | null;
  uploaded_at: string;
  extracted_text?: string | null;
}

export interface Message {
  id: number;
  step_id: string;
  direction: "in" | "out";
  channel: string;
  recipient: string | null;
  subject: string | null;
  body: string;
  status: string;
  approved_at: string | null;
  sent_at: string | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface LadderStep {
  id: string;
  name: string;
  channel: string;
  recipient_role: string | null;
  wait_days: number | null;
  state: "done" | "current" | "future" | "skipped";
}

export interface Reason {
  code: string;
  params: Record<string, string | number | null>;
}

export interface Deadline {
  id: string;
  rule: string;
  due: string | null;
  days_left: number | null;
  warn: boolean;
  late: boolean;
}

export interface CaseSummary {
  id: number;
  title: string;
  case_type: string | null;
  country: string | null;
  region: string | null;
  language: string;
  company: string | null;
  amount: string | null;
  amount_display: string | null;
  currency: string | null;
  status: CaseStatus;
  playbook_id: string | null;
  current_step: string | null;
  next_action_at: string | null;
  created_at: string;
  waiting_for: WaitingFor;
  generic_playbook: boolean;
  step_name: string | null;
  ladder: LadderStep[];
  deadline_warning: boolean;
}

export interface Pending {
  type: Exclude<WaitingFor, null>;
  missing?: string[];
  items?: ChecklistItem[];
  draft?: { message_id: number; recipient: string | null; subject: string | null; body: string; channel: string };
  message_id?: number;
  channel?: string;
  note?: string;
  step?: string;
}

export interface CaseDetail extends Omit<CaseSummary, "deadline_warning"> {
  description: string;
  playbook_version: string | null;
  facts: Fact[];
  evidence: Evidence[];
  messages: Message[];
  pending: Pending | null;
  pending_draft: Message | null;
  deadlines: Deadline[];
  reasons: Reason[];
  sources: { title: string; url: string | null }[];
  text_direction: "ltr" | "rtl";
}

export interface RunOut {
  case_id: number;
  waiting_for: WaitingFor;
  pending: Pending | null;
  warnings: string[];
}

export interface ReplyOut extends RunOut {
  verdict: "resolved" | "partial" | "refused" | "no_reply" | null;
  reason: string | null;
  promise: string | null;
  promise_date: string | null;
  condition: string | null;
}

export interface Segment {
  text: string;
  kind: "text" | "fact" | "blank";
  key: string | null;
}

export interface ReviewFact {
  key: string;
  value: string;
  display: string[];
  confidence: number;
  source_evidence_id: number | null;
  source_filename: string | null;
  used: boolean;
}

export interface Check {
  id: "facts" | "blanks" | "tone" | "disclaimer" | "no_secrets";
  ok: boolean;
  detail: string[];
}

export interface Problem {
  kind: "number" | "date" | "id";
  wrong: string;
  expected: string[];
}

export interface Review {
  message: Message;
  case_id: number;
  language: string;
  locale: string;
  text_direction: "ltr" | "rtl";
  subject_segments: Segment[];
  body_segments: Segment[];
  facts: ReviewFact[];
  blanks: string[];
  checks: Check[];
  problems: Problem[];
  can_approve: boolean;
  template_languages: string[];
  step_name: string | null;
}

export interface Preview {
  language: string;
  available: boolean;
  text_direction: "ltr" | "rtl";
  subject: string | null;
  body: string | null;
}

export interface ChecklistItem {
  id: string;
  title: string;
  detail: string;
  urgent: boolean;
}

export interface Checklist {
  country: string;
  items: ChecklistItem[];
  warnings: string[];
  sources: { title: string; url?: string }[];
}

export interface Country {
  code: string;
  currency: string | null;
  local_pack: boolean;
  packs: Record<string, string>;
  regions: string[];
}

export interface Settings {
  llm_base_url: string;
  model_smart: string;
  model_fast: string;
  has_llm_api_key: boolean;
  is_cloud: boolean;
  email_mode: string;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  has_smtp_password: boolean;
  default_country: string | null;
  default_language: string;
  enabled_letter_languages: string[];
  demo_mode: boolean;
  version: string;
}

export interface TimelineEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}
