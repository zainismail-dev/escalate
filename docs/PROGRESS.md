# Progress

One line per task from `CLAUDE_CODE_PLAN.md`: task id, what was built, test result.

- **1.1** — uv project, deps, layout, .env.example, CI, smoke test — 1 passed; ruff clean; mypy clean
- **1.2** — Settings, 5 models + CaseStatus, session factory, Alembic init migration, log_event — 8 passed; ruff clean
- **1.3** — OpenAI-compatible client with 429 backoff, ask_json with repair+retry, is_cloud, FakeLLM, llm_ping script — 21 passed; ruff clean (Ollama ping skipped: no model pulled)
- **1.4** — Fernet-encrypted evidence store with SHA-256, OCR (Tesseract/pypdf/eml/txt), needs_review below 60 — 30 passed, 1 skipped (real Tesseract OCR: binary not installed locally; runs in CI)
