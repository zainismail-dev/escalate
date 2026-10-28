# Escalate — Claude Code Build Plan (4 weeks)

A week-by-week list of tasks for Claude Code. Each task has a **prompt to paste**,
a **done-when** check you verify yourself, and a **commit message**.

---

## Before you start (once, ~30 min)

1. Create an empty GitHub repo `escalate` and clone it.
2. Put `CLAUDE.md` in the repo root. Claude Code reads it at the start of every session.
3. Export the build-plan doc as Markdown and save it as `docs/BUILD_PLAN.md`.
   Task prompts refer to its section numbers (e.g. "section 6").
4. Install Python 3.12, `uv`, Docker, Tesseract, and Ollama, then pull one open
   7–8B instruct model with `ollama pull <model>`.
5. Open Claude Code in the repo folder.

### Working rhythm (every task)
- **One task per session.** Start a fresh conversation for each task so context stays clean.
- **Plan first.** Begin with: *"Read CLAUDE.md and section X of docs/BUILD_PLAN.md. Propose a plan and the files you'll touch. Don't write code yet."* Approve or correct the plan, then say *"Go."*
- **Verify yourself.** Run the done-when checks. If something fails, paste the error back to Claude Code.
- **Commit** after every task that passes. Push at the end of each day.
- If Claude Code goes off track twice on the same task, stop and split the task smaller.

---

## Week 1 — Foundations
**Gate at end of week:** CI is green, evidence uploads work, and facts are extracted from a sample case.

### Task 1.1 — Project skeleton and CI
**Prompt**
```
Read CLAUDE.md and section 4 of docs/BUILD_PLAN.md.
Set up the project: uv project for Python 3.12, all dependencies from section 4
(runtime + dev), the folder layout from CLAUDE.md with __init__.py files,
.env.example exactly as in section 4, .gitignore (Python, .env, data/, secrets/),
MIT LICENSE, a placeholder README, pyproject config for ruff and mypy, and
.github/workflows/ci.yml (ruff, playbook validate, pytest).
Add one smoke test that imports the package. Make CI pass locally.
```
**Done when:** `uv run pytest -q` passes, `uv run ruff check .` is clean, and GitHub Actions is green after you push.
**Commit:** `chore: project skeleton, tooling and CI`

### Task 1.2 — Settings and database
**Prompt**
```
Read section 5 of docs/BUILD_PLAN.md.
1) escalate/config.py: pydantic-settings Settings reading every variable in .env.example.
2) escalate/db/models.py: the five models from section 5 (cases, case_facts,
   evidence, messages, events) with the CaseStatus enum. Use ISO codes; no
   country or currency defaults.
3) escalate/db/session.py: engine + session factory from DATABASE_URL.
4) Alembic set up to read DATABASE_URL; create the initial migration.
5) escalate/db/events.py: helper log_event(session, case_id, type, payload).
Tests: create a case with facts, evidence, a message and an event in an in-memory
SQLite DB; cascade delete removes children.
```
**Done when:** `alembic upgrade head` creates the tables, and the tests pass.
**Commit:** `feat(db): models, migrations and event log`

### Task 1.3 — LLM client (free by default)
**Prompt**
```
Read the "Global and free by design" section and section 3 of docs/BUILD_PLAN.md.
Build escalate/llm/:
- client.py: one OpenAI-compatible client using LLM_BASE_URL, LLM_API_KEY,
  MODEL_SMART, MODEL_FAST. Methods: complete(prompt, slot="smart"|"fast").
- structured.py: ask_json(prompt, model_cls, slot) -> validated Pydantic object.
  Extract JSON from the reply, validate, and on failure retry up to 2 times with
  the validation error appended. Handle HTTP 429 with exponential backoff.
- privacy.py: if CLOUD_PRIVACY_WARNING is true and LLM_BASE_URL is not localhost,
  expose is_cloud() so the UI can warn.
- tests/fakes/fake_llm.py: a scripted fake used by all unit tests.
Tests: JSON repair/retry path, 429 backoff (mocked), is_cloud().
Add a manual script scripts/llm_ping.py that sends one prompt to the configured model.
```
**Done when:** tests pass offline, and `uv run python scripts/llm_ping.py` gets an answer from local Ollama.
**Commit:** `feat(llm): OpenAI-compatible client with structured output and retries`

### Task 1.4 — Evidence storage and OCR
**Prompt**
```
Read section 9 (Evidence + OCR) of docs/BUILD_PLAN.md.
Build escalate/evidence/:
- store.py: save_upload(case_id, filename, bytes) -> Evidence row. Compute
  SHA-256, encrypt with Fernet (FERNET_KEY), write to EVIDENCE_DIR/<case_id>/<sha>.bin,
  and log an evidence_added event. load_plain(evidence) decrypts.
- ocr.py: extract_text(evidence) for images (pytesseract, lang=settings.OCR_LANGS,
  return mean confidence), PDFs (pypdf), .eml (email module), and .txt.
  If confidence < 60, mark needs_review=True; don't call any cloud API here.
Tests with small fixture files in tests/fixtures/ (a generated receipt PNG, a PDF,
an .eml). Verify the encrypted file on disk is not readable as plain text.
```
**Done when:** tests pass, and OCR returns readable text from the fixture receipt.
**Commit:** `feat(evidence): encrypted storage and OCR`

### Task 1.5 — Playbooks: schema, loader, resolver, validator
**Prompt**
```
Read section 6 of docs/BUILD_PLAN.md (including "Global layout").
1) schema/playbook.schema.json covering every field in the example YAML
   (id, version, country, regions, case_type, last_verified, required_facts,
   optional_facts, deadlines, steps with channel/template/wait_days/on_no_reply/
   on_refused/when/proof_required/attachments, sources (min 1)).
2) escalate/playbooks/loader.py: load + validate all YAML, cache by id.
3) resolver.py: resolve(country, region, case_type, company=None) with fallback
   company -> region -> country -> intl/generic.
4) validate.py CLI: fails on schema errors, missing templates, step targets that
   don't exist, missing sources; warns when last_verified is older than 12 months.
5) Add playbooks/intl/generic/{refund_refused,subscription_cancel,scam}.yaml and
   playbooks/pk/ecommerce/refund_refused.yaml from section 6, with stub templates
   so validation passes.
Tests for the resolver fallbacks and for each validator failure.
```
**Done when:** `uv run python -m escalate.playbooks.validate playbooks/` passes, and resolver tests pass.
**Commit:** `feat(playbooks): schema, loader, resolver, validator, first playbooks`

### Task 1.6 — Intake: fact extraction
**Prompt**
```
Read sections 7 and 8 (prompt 1) of docs/BUILD_PLAN.md.
Create escalate/llm/prompts/extract_facts.txt from section 8 and an intake
service escalate/agent/intake.py:
- extract(case, user_text, evidence_texts, required_facts) -> facts + missing,
  via ask_json with a Pydantic model.
- Save each fact to case_facts with source_evidence_id and confidence.
- Never store a value that the model marked as a guess (confidence < 0.5 goes to missing).
Create evals/cases/ with 10 golden cases as JSON (include "broken LED returned,
8 months waiting for company claim approval"), and evals/run.py that scores
field accuracy for extraction.
Unit tests use the fake LLM.
```
**Done when:** unit tests pass, and `uv run python -m evals.run --suite extraction` runs against Ollama and prints a score.
**Commit:** `feat(agent): fact extraction and first golden cases`

---

## Week 2 — First full case, end to end
**Gate at end of week:** the broken-LED case runs from intake to sent email, through a timeout follow-up, to the legal notice draft.

### Task 2.1 — Classification and drafting
**Prompt**
```
Read sections 7 and 8 (prompts 2 and 3) of docs/BUILD_PLAN.md.
- prompts/classify.txt and agent/classify.py: case_type, country, region,
  language, urgent. Then call the playbook resolver and store playbook id/version.
- Template rendering: escalate/templates_engine.py with Jinja2 StrictUndefined.
  A missing placeholder raises an error and blocks the draft.
- prompts/draft.txt and agent/draft.py: render the step's template with facts,
  then ask the smart model to polish tone and language while keeping structure.
  Save the result as a Message(status="draft").
- Add templates/_shared/disclaimer.md.j2 and append it to every draft.
Tests with the fake LLM: unknown country falls back to intl/generic; missing
fact blocks drafting.
```
**Done when:** tests pass, and a draft for the LED golden case looks right when printed.
**Commit:** `feat(agent): classification and template-based drafting`

### Task 2.2 — Fact check and approval gate
**Prompt**
```
Read sections 8 (prompt 5) and 9 (Approval gate) of docs/BUILD_PLAN.md and
rule 1 in CLAUDE.md.
- agent/fact_check.py: code check first (regex every number, date and ID in the
  draft; each must appear in case_facts), then the fast-model check from prompt 5.
  Return a list of unsupported claims.
- channels/gate.py: NotApproved and require_approval(msg) exactly as in section 9.
- Service functions approve_message(id, edited_body=None) (the ONLY place that
  sets approved_at), reject_message(id, reason).
Tests: an invented amount is caught; sending is blocked for draft, rejected, and
already-sent messages; approve sets approved_at and logs an event.
```
**Done when:** the gate tests pass, and `grep -rn "approved_at =" escalate/` shows only `approve_message`.
**Commit:** `feat(safety): fact check and approval gate`

### Task 2.3 — Email sending (free)
**Prompt**
```
Read section 9 (Email) of docs/BUILD_PLAN.md.
- channels/email_smtp.py: send via Gmail SMTP with SMTP_USER + SMTP_APP_PASSWORD
  (SSL, port 465), attachments supported. Calls require_approval first.
- channels/email_gmail.py: optional Gmail API sender (scope gmail.send only),
  same interface.
- channels/post.py and court.py: render a printable PDF; mark sent only when the
  user uploads proof (courier/registry receipt) as evidence.
- channels/__init__.py: get_channel(name) registry. Sets sent_at, logs message_sent,
  and is idempotent.
Tests use a fake SMTP server (aiosmtpd or a mock) — no real email in tests.
```
**Done when:** tests pass, and a manual test sends one approved email to your own address.
**Commit:** `feat(channels): SMTP, Gmail API, post and court channels`

### Task 2.4 — Scheduler and reply handling
**Prompt**
```
Read section 9 (Scheduler) and prompt 4 in section 8 of docs/BUILD_PLAN.md.
- scheduler/jobs.py: APScheduler BackgroundScheduler with SQLAlchemyJobStore.
  schedule_wake(case_id, step_id, when) uses job id "case-<id>-step-<step>"
  (replace_existing=True). Daily deadline scan creates "deadline in N days"
  events at <= 10 days left.
- prompts/judge_reply.txt and agent/judge_reply.py: verdict resolved | partial |
  refused | no_reply; a vague promise with no date counts as refused.
- agent/pick_next.py: follow on_no_reply / on_refused from the playbook; None at
  the end of the ladder.
Tests with freezegun: a 7-day wait fires once on day 7; it still fires after
recreating the scheduler (restart); the LED promise "when claim approved" is judged refused.
```
**Done when:** the time-travel tests pass.
**Commit:** `feat(scheduler): wake-ups, deadlines and reply judging`

### Task 2.5 — Wire the LangGraph agent
**Prompt**
```
Read section 7 of docs/BUILD_PLAN.md.
Build escalate/agent/graph.py exactly as the skeleton: CaseState, all nodes wired to
the services from earlier tasks, interrupt() at approval and wait, SqliteSaver
checkpointer with thread_id = str(case_id).
Add escalate/agent/runner.py with start_case(), resume_with_answers(),
resume_with_decision(), resume_with_reply(), resume_timeout(), which the
scheduler and the API call.
Integration test (fake LLM, fake SMTP, freezegun): LED case -> facts -> draft
-> approve -> sent -> 5 days pass -> follow-up draft -> approve -> 15 days ->
legal notice draft. Assert the event log order.
```
**Done when:** the integration test passes.
**Commit:** `feat(agent): LangGraph case graph and runner`

### Task 2.6 — API and minimal UI
**Prompt**
```
Read section 10 of docs/BUILD_PLAN.md.
- FastAPI routes for all 12 endpoints in section 10, with Pydantic request and
  response models. Start the scheduler on app startup.
- Streamlit ui/app.py with three pages for now: New case (text + uploads +
  country/region pickers), Review draft (editable, facts shown, Approve / Edit /
  Reject), Case dashboard (status, next action, timeline).
- Show a privacy banner when llm.privacy.is_cloud() is true.
API tests with FastAPI TestClient.
```
**Done when:** you can run the LED case by hand in the browser up to a sent email, then record a rough screen capture.
**Commit:** `feat: API and first Streamlit screens`

---

## Week 3 — Breadth: all case types, global packs, exports
**Gate at end of week:** all 3 case types work, 4 country packs plus generic validate, and the PDF case file exports.

### Task 3.1 — Pakistan pack complete
**Prompt**
```
Read section 6 of docs/BUILD_PLAN.md.
Write the 5 Pakistan templates in templates/pk/en/ (seller demand, platform
escalation, 15-day legal notice, consumer court complaint, condonation of delay)
and Urdu versions in templates/pk/ur/. Use only playbook facts as placeholders.
Add the court_filing_limit deadline handling: when filing is late, attach the
condonation template automatically. Keep sources in the YAML.
Tests: render each template with LED facts; a late case includes condonation.
```
**Done when:** validation passes, and the rendered notice reads correctly. Plan to have a lawyer review the templates later, in task 4.2.
**Commit:** `feat(playbooks): complete Pakistan refund pack`

### Task 3.2 — Subscription and scam flows
**Prompt**
```
Read the Global section and section 7 of docs/BUILD_PLAN.md.
- Generic subscription_cancel playbook + templates (cancel request, final notice
  with charges listed, card-issuer dispute letter, authority complaint).
- Scam flow: urgent_checklist node + UI page that shows time-critical steps first
  (call bank/card issuer, block card, change passwords, report to the national
  body), loaded from playbooks/<cc>/scam_checklist.yaml with a generic fallback.
  Never ask for passwords, PINs or OTPs; warn about "recovery" scammers.
- Scam letters: bank dispute/fraud report and police/national report drafts.
Tests for both flows end to end with the fake LLM.
```
**Done when:** both flows pass their integration tests, and the scam case shows the checklist before any letter.
**Commit:** `feat: subscription-cancel and scam flows`

### Task 3.3 — Country packs: India, UK, US
**Prompt**
```
Create country packs for in, gb and us following the pk pack structure:
refund_refused for each, plus scam_checklist.yaml. Use placeholders for authority
names/addresses where you are not certain, and add a TODO in each file listing
the facts a contributor must verify from official sources. Do NOT invent
URLs, phone numbers or legal section numbers — leave them as TODO.
Add docs/CONTRIBUTING-PLAYBOOKS.md explaining how to verify and submit a pack.
```
**Done when:** validation passes. Then verify each TODO yourself from official government sites, or open issues labelled `country:<cc>` and `good first issue` for contributors.
**Commit:** `feat(playbooks): starter packs for India, UK, US`

### Task 3.4 — Localisation
**Prompt**
```
Add escalate/i18n/formatting.py using Babel: format_money(amount, currency,
locale), format_date(d, locale). Move all UI strings to locales/en.json, load
them in Streamlit via a t("key") helper, and add a language selector. Add
locales/ur.json as the first translation (keys only where unsure).
Drafts use case.language. Test formatting for PKR, INR, GBP, USD.
```
**Done when:** switching the UI language changes the labels, and amounts format correctly.
**Commit:** `feat(i18n): Babel formatting and translatable UI`

### Task 3.5 — Timeline, replies, PDF export, remaining screens
**Prompt**
```
Read sections 9 (PDF case file) and 10 of docs/BUILD_PLAN.md.
- export/case_pdf.py: Jinja2 HTML -> WeasyPrint. Pages: cover, facts with sources,
  dated timeline, full messages, evidence thumbnails with SHA-256.
- UI pages: Log a reply (shows the verdict), My cases (filters), Settings
  (LLM endpoint test button, email mode, languages), Questions (missing facts).
- Deadline warnings shown in red on the dashboard.
Tests: PDF builds and contains the case number and every event date.
```
**Done when:** the LED case exports a clean PDF, and every screen works by hand.
**Commit:** `feat: case PDF export and full UI`

### Task 3.6 — Golden set to 50
**Prompt**
```
Extend evals/ to 50 golden cases across at least 5 countries and 3 languages,
covering all 3 case types, plus 40 sample company replies for the reply judge.
evals/run.py --suite all reports: extraction accuracy, classification accuracy,
unsupported facts per draft, tone flags, reply-judge accuracy; writes
evals/report.md.
```
**Done when:** the eval report is generated against your local model.
**Commit:** `test(evals): 50-case golden set and full report`

---

## Week 4 — Quality, packaging, launch
**Gate at end of week:** v0.1.0 is tagged, the README has a GIF, and a fresh install works.

### Task 4.1 — Hit the eval targets
**Prompt**
```
Run evals/run.py --suite all and read evals/report.md. Targets: extraction
>= 95%, classification >= 95%, 0 unsupported facts, 0 tone flags, reply judge
>= 90%. For each miss, propose the smallest fix (prompt wording, template
structure, code-side check, or a few-shot example), apply it, and re-run.
Don't lower targets. Record before/after numbers in evals/report.md.
```
**Done when:** the targets are met with at least one recommended free local model. List that model in the README.
**Commit:** `perf(evals): reach v0.1 quality targets`

### Task 4.2 — Safety hardening
**Prompt**
```
Audit the codebase against the rules in CLAUDE.md. Specifically:
- Search every path that could send; confirm all go through require_approval.
- PII masking in logs and drafts (cards, IBANs, national IDs).
- One-click case deletion removes DB rows, evidence files and scheduler jobs.
- Rate limit new cases; reject cases with no evidence and repeated recipients
  (harassment pattern).
- DEMO_MODE: no real sending, auto-delete after 24h, 5 MB upload cap.
Write a test for each item and a SECURITY.md.
```
**Done when:** all safety tests pass. Separately, send the Pakistan templates to a lawyer or consumer-rights group for review.
**Commit:** `fix(security): safety audit, PII masking, demo mode`

### Task 4.3 — Docker one-command install
**Prompt**
```
Read section 12 of docs/BUILD_PLAN.md.
Write the Dockerfile (python:3.12-slim, tesseract + language packs, WeasyPrint
system libs, uv sync --frozen) and docker-compose.yml with ollama, api and ui.
Add a Makefile: `make setup` (copy .env, generate FERNET_KEY, pull the model),
`make up`, `make test`, `make evals`. Add a CI job that builds the image.
```
**Done when:** on a second machine (or a fresh clone in a new folder), `make setup && make up` works, and a case can be opened.
**Commit:** `build: Docker image, compose and Makefile`

### Task 4.4 — README and community files
**Prompt**
```
Read section 13 of docs/BUILD_PLAN.md.
Write README.md following the outline (one-liner, GIF placeholder at
docs/demo.gif, why it exists, 3-command quick start, how it works with a
Mermaid architecture diagram, safety, supported countries table, add-your-country
link, roadmap, contributing, license). Add CONTRIBUTING.md, CODE_OF_CONDUCT.md,
issue templates (bug, new playbook, playbook correction), and a
docs/good-first-issues.md list of 10 issues I can open.
```
**Done when:** the README renders well on GitHub. Record the demo GIF yourself and save it to `docs/demo.gif`.
**Commit:** `docs: README, contributing guide and templates`

### Task 4.5 — Release v0.1.0
**Prompt**
```
Prepare release v0.1.0: update version, write CHANGELOG.md, make sure CI is
green, and draft GitHub release notes (features, supported countries, known
limits, how to help). Give me the exact git commands to tag and push.
```
**Done when:** the tag is pushed, the GitHub release is published, and the 10 good-first issues are opened.
**Commit:** `chore(release): v0.1.0`

### After launch (you, not Claude Code)
- Post on LinkedIn, X and Reddit (section 13), using your cousin's LED story as the hook.
- Optional free hosted demo (section 12); check current free-tier terms first.
- Triage issues daily for the first two weeks; merge playbook PRs only when they cite official sources.

---

## Tips for working with Claude Code on this project
- If a task grows past ~10 files, ask Claude Code to split it, and do the halves in separate sessions.
- Paste exact error output rather than describing it.
- Ask *"run the tests and show me the output"* before accepting "done".
- Keep `CLAUDE.md` updated: when you make a decision (for example, the recommended model), add it there so every future session knows.
- Never paste real personal data, API keys or passwords into the chat; use the fake data in `evals/`.
