# CLAUDE.md — Escalate

## What this project is
Escalate is an open-source, self-hostable AI agent that runs a consumer complaint
(refund refused, subscription won't cancel, scam) from first message to consumer court,
using country "playbooks". It drafts every message, tracks deadlines, follows up and
escalates — but the USER APPROVES EVERY OUTGOING MESSAGE.

Full spec: `docs/BUILD_PLAN.md` (exported from the build-plan doc). Read the relevant
section before starting any task. Section numbers in task prompts refer to that file.

## Non-negotiable rules
1. **No sending without approval.** Only `escalate/channels/gate.py::require_approval`
   can unlock a send. Never add a code path that sends without `approved_at` set.
   The LLM never gets a tool that sends.
2. **Facts only.** Drafts may only use values from `case_facts`. Never invent amounts,
   dates, IDs, laws or addresses.
3. **$0 by default.** No paid service may be required. LLM access goes through the
   OpenAI-compatible client in `escalate/llm/` (default: local Ollama). Do not add
   provider-specific SDKs (anthropic, google-genai, etc.) as hard dependencies.
4. **Global.** Never hard-code a country, currency, language or region. Use ISO codes
   (3166-1, 3166-2, 4217, 639-1) and the playbook resolver
   (company → region → country → `intl/generic`).
5. **Privacy.** Evidence files are encrypted at rest (Fernet). Never log full card
   numbers, IBANs, national IDs, passwords or OTPs. Never ask users for passwords/PINs/OTPs.
6. **Not legal advice.** Generated letters and exports include the notice from
   `templates/_shared/disclaimer.md.j2`.

## Stack
Python 3.12 · uv · LangGraph (SQLite checkpointer) · `openai` SDK against any
OpenAI-compatible endpoint · Pydantic · FastAPI · SQLAlchemy 2 + Alembic (SQLite default)
· APScheduler (SQLAlchemy job store) · pytesseract · pypdf · Jinja2 · Babel ·
WeasyPrint · cryptography · Streamlit · pytest + freezegun · Ruff + mypy · Docker.

## Layout
```
escalate/
  agent/      LangGraph state + nodes (intake, ask_missing, classify, urgent_checklist,
              draft, fact_check, approval, send, wait, judge_reply, pick_next)
  llm/        client.py (OpenAI-compatible), prompts/*.txt, structured.py (JSON + retry)
  playbooks/  loader.py, resolver.py, validate.py (CLI)
  scheduler/  jobs.py
  channels/   gate.py, email_smtp.py, email_gmail.py, post.py, court.py
  evidence/   store.py (encrypt/hash), ocr.py
  export/     case_pdf.py
  db/         models.py, session.py
  api/        main.py, routes/*.py
  i18n/       formatting.py (Babel)
ui/           Streamlit app (talks to the API only)
playbooks/    <cc>/<sector>/<case_type>[.<company>].yaml ; intl/generic/*
templates/    <cc>/<lang>/*.md.j2 ; _shared/
locales/      UI strings, <lang>.json
schema/       playbook.schema.json
evals/        golden cases + run.py
tests/
```

## Commands
- Install: `uv sync`
- Run API: `uv run uvicorn escalate.api.main:app --reload`
- Run UI: `uv run streamlit run ui/app.py`
- Tests: `uv run pytest -q`
- Lint/type: `uv run ruff check . && uv run ruff format --check . && uv run mypy escalate`
- Validate playbooks: `uv run python -m escalate.playbooks.validate playbooks/`
- Evals: `uv run python -m evals.run --suite all`
- Migrations: `uv run alembic revision --autogenerate -m "<msg>"` then `uv run alembic upgrade head`

## How to work in this repo
- Before coding, read the task's spec section and list the files you will touch.
- Small steps: write or update tests with each change; run tests + ruff before saying done.
- Use a fake LLM (`tests/fakes/fake_llm.py`) in unit tests — tests must pass offline.
- Use `freezegun` for anything time-based. Never `time.sleep` in tests.
- Type hints everywhere; Pydantic models for every LLM output.
- Keep functions small; no new dependency without a one-line reason in the PR/commit.
- When a task is done, report: files changed, tests added, commands run and their result,
  and anything left open.
- Commit messages: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
