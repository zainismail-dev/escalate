# Progress

One line per task from `CLAUDE_CODE_PLAN.md`: task id, what was built, test result.

- **1.1** — uv project, deps, layout, .env.example, CI, smoke test — 1 passed; ruff clean; mypy clean
- **1.2** — Settings, 5 models + CaseStatus, session factory, Alembic init migration, log_event — 8 passed; ruff clean
- **1.3** — OpenAI-compatible client with 429 backoff, ask_json with repair+retry, is_cloud, FakeLLM, llm_ping script — 21 passed; ruff clean (Ollama ping skipped: no model pulled)
- **1.4** — Fernet-encrypted evidence store with SHA-256, OCR (Tesseract/pypdf/eml/txt), needs_review below 60 — 30 passed, 1 skipped (real Tesseract OCR: binary not installed locally; runs in CI)
- **1.5** — JSON schema, loader, resolver (company→region→country→generic), validator CLI, 3 generic + PK playbooks with templates — 52 passed, 1 skipped; validator OK 4 playbooks
- **1.6** — extract_facts prompt, intake extract/save_answers, 10 golden cases incl. broken LED, evals/run.py extraction suite — 59 passed, 1 skipped; oracle eval 100% (real-model eval: manual)
- **2.1** — classify prompt+service with ISO checks, resolver hookup, StrictUndefined template engine, draft prompt+service, disclaimer — 73 passed, 1 skipped; validator OK
- **2.2** — code+model fact check, require_approval gate, approve/reject/edit services (only approve_message sets approved_at) — 92 passed, 1 skipped; grep approved_at= shows only approve_message
- **2.3** — SMTP (SSL 465) + Gmail API email, post/court/web_form with proof-based confirm, idempotent send registry, printable PDF helper — 110 passed, 2 skipped (WeasyPrint/Tesseract need system libs; run in CI)
- **2.4** — APScheduler with SQLAlchemy job store, schedule_wake/cancel, daily deadline scan, judge_reply (undated promise=refused), pick_next — 124 passed, 2 skipped; freezegun wake/restart tests pass
- **2.5** — LangGraph case graph (11 nodes, SqliteSaver, interrupts), runner start/resume/retry/withdraw, LED end-to-end integration test — 135 passed, 2 skipped; LED case intake→seller→platform→legal notice→court draft passes
- **2.6** — FastAPI (12 spec endpoints + start/ack/retry/confirm/printable/health), scheduler on startup, Streamlit New case/Review/Dashboard with privacy banner — 147 passed, 2 skipped; API and UI booted headless
- **3.1** — 5 Pakistan templates in en and ur, condonation auto-attached when late, Unicode-digit fact check, en fallback required — 161 passed, 2 skipped; validator OK
- **3.2** — subscription_cancel templates (cancel, final notice with charges, card dispute, authority), scam checklist-first flow + UI page, bank/police/national fraud letters, no-secrets validator rule — 170 passed, 2 skipped; both flows pass end to end
- **3.3** — IN/GB/US refund packs + templates, PK/IN/GB/US scam checklists (TODOs, no URLs/phones/sections), checklist validation, CONTRIBUTING-PLAYBOOKS.md — committed with 1 stale resolver test failing (183 passed); fixed in the next commit, 184 passed, 2 skipped; validator OK 7 playbooks (URL warnings expected)
- **3.4** — Babel money/date formatting (PKR/INR/GBP/USD tested), all UI strings in locales/en.json via t(), language selector, partial ur.json with RTL — 198 passed, 2 skipped
- **3.5** — case PDF (cover, facts+sources, timeline, messages, evidence thumbnails+SHA-256), Questions/Log reply/My cases/Settings screens, PDF download + withdraw on dashboard — 205 passed, 3 skipped; ruff+mypy clean; validator OK; PDF render test runs in CI only (no Pango locally)
- **3.6** — 50 golden cases (12 countries, 6 languages, 3 case types), 40 sample replies, evals --suite all (extraction, classification, unsupported facts, tone, reply judge) writing evals/report.md, code tone check — 215 passed, 3 skipped; ruff+mypy clean; validator OK; report.md is an oracle harness run; real-model run is manual
- **4.1** — PARTIAL: model-independent fixes (tone gate in fact check, few-shot reply judge, clearer classify/extract prompts), before/after History in evals/report.md — ; ruff+mypy clean; validator OK; targets NOT verified: no local model available (see MANUAL_STEPS)
- **4.2** — safety audit: AST-checked approval on every send path, PII masking (cards/IBAN/CNIC/Aadhaar/SSN/NI/OTP) in logs+storage+drafts, one-click delete, rate limit, evidence required, repeated-recipient guard, DEMO_MODE, SECURITY.md — 248 passed, 3 skipped; ruff+mypy clean; validator OK
