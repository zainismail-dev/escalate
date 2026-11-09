# Changelog

All notable changes to Escalate. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Hosted beta models are `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (Groq retired llama-3.x).
- Letters name the product, what the trader said, the remedy with its amount, the days to reply
  with the date, and the pack's legal basis (UK: Consumer Rights Act 2015). Dates are always the
  locale's long format. Packs can declare `legal_basis`; the UK pack now requires `product`.
- A model's bad JSON is retried once (it was twice), more strictly.

### Fixed
- Fact check: "14-day" is a number and a word, not an unknown ID; the days to reply are in the
  trusted letter; the model check sees that letter too; non-breaking hyphens and narrow spaces
  count as ordinary ones. Rejections log reason categories, never content.
- Failed AI calls no longer count against the daily limits.
- A permanent AI error (unknown model, bad key) fails once with "The AI service is misconfigured".
- Unexpected errors carry CORS headers, so the browser no longer reads them as "can't reach the
  server" and the hosted app no longer repeats the request up to 11 times.
- Hosted copy (server wake-up, "Encrypted on our server", Supabase in Ireland); the timeline
  collapses retries and shows local times; ladder step names are capitalised.

### Security
- Sign-in only follows same-site `next` paths (backslash, tab and newline tricks refused).
- Hosted: only a Google-verified email (`AUTH_PROVIDERS`) matches an invite; turn the Supabase
  Email provider off.
- No global lock around agent runs; AI requests time out after 60 s (90 s per call in all);
  at most `AGENT_CONCURRENCY` runs at once; `/health` always answers.
- Token-aware daily AI budgets, a daily limit on failed AI calls, 10 files per case and 40k
  characters of evidence per prompt.
- Per-user storage cap (50 MB), 10 MB files, one upload at a time, rate-limited PDF/export
  downloads; no database connection held during OCR.
- Supabase session cookie: Secure, SameSite=Lax, 7 days.
- Closed cases can't be started or continued; the open-case limit is atomic and covers reopening.
- Rate limits use the address Render's proxy saw, never a spoofable `X-Forwarded-For` entry;
  limiter memory is bounded.
- Hosted mode refuses `ALLOWED_HOSTS` with `*` or empty entries.
- `/internal/tick` is a 404 for every method without the secret; evidence and event ids in the
  API are UUIDs; a provider 400 drops JSON mode for that call only.

### Fixed (smoke test)
- The letter's subject appears once (email subject / PDF heading), never in the body.
- Hosted: the approve button says "Approve"; no local-only wording; a missing case shows
  "Case not found".
- "Within 30 days of the purchase"; step names capitalised in headings and labels; recipient
  addresses wrap between their parts.

## [0.1.0] - 2026-10-28

First public release.

### Added
- **Case agent** (LangGraph, SQLite checkpoints): intake → questions → classify → draft →
  fact check → approval → send → wait → judge reply → next step, for three case types:
  refund refused, subscription won't cancel, and scams.
- **Playbooks** with JSON Schema, a resolver (company → region → country → generic) and a
  validator CLI used in CI. Packs: generic international ladders for all three case types;
  Pakistan refund pack (seller → marketplace → 15-day legal notice → District Consumer Court,
  with condonation of delay when late) in English and Urdu; starter refund packs for India,
  the UK and the US; scam checklists for PK, IN, GB, US and a generic fallback.
- **Approval gate**: nothing is sent without an explicit approval; every channel checks it.
- **Fact check**: every number, date and ID in a draft must come from the case facts (code
  check, then a model check); a tone check blocks threats and insults.
- **Channels**: Gmail SMTP (app password), optional Gmail API, printable post and court letters
  marked sent only with uploaded proof, web forms.
- **Scheduler** (APScheduler, persistent job store): follow-up wake-ups that survive restarts,
  and daily deadline warnings from 10 days before a filing limit.
- **Evidence**: Fernet-encrypted storage with SHA-256, OCR (Tesseract), PDF and email text.
- **PDF case file**: cover, facts with sources, dated timeline, messages, evidence thumbnails
  and hashes.
- **API** (FastAPI) and **web UI** (Streamlit): new case, scam "do this now" page, questions,
  draft review, dashboard with deadline warnings, log a reply, my cases, settings.
- **Localisation**: Babel money and date formatting, translatable UI (English, partial Urdu).
- **Privacy and safety**: masking of card numbers, IBANs, national IDs, passwords and OTPs in
  logs, stored text and drafts; one-click case deletion; rate limit on new cases; evidence
  required to start; refusal of repeated letters to one recipient across cases; demo mode.
- **Evals**: 50 golden cases (12 countries, 6 languages) and 40 sample replies, with a report
  for extraction, classification, unsupported facts, tone and reply-judge accuracy.
- **Packaging**: Dockerfile, docker compose (Ollama, API, UI), Makefile, GitHub Actions CI.
