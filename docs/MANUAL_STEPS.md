# Manual steps

Things the autonomous build could not do because they need you, a real account, or hardware
that was not available. Each item names the task it came from.

- [ ] **1.3 — Pull a local model and ping it.** No Ollama model was pulled during the build.
  Run `ollama pull <model>` (an open 7–8B instruct model), set `MODEL_SMART`/`MODEL_FAST` in
  `.env`, then `uv run python scripts/llm_ping.py` and confirm you get an answer.
- [ ] **1.4 — Install Tesseract locally.** It was not installed on the build machine, so
  `test_real_ocr_reads_fixture_receipt` skipped locally (CI installs Tesseract and runs it).
  Install `tesseract` + language packs (e.g. `urd`), then run `uv run pytest tests/test_evidence.py`.
- [ ] **1.6 / 3.6 / 4.1 — Run the evals against a real local model.** Only the offline
  `--llm oracle` harness check ran during the build (it always scores 100% by design). After
  pulling a model: `uv run python -m evals.run --suite all`, then read `evals/report.md`.
- [ ] **2.3 — Send one real approved email to yourself.** Not done during the build (no
  credentials, and the build never sends real email). Create a Gmail app password, set
  `SMTP_USER` / `SMTP_APP_PASSWORD`, open a test case with your own address as the seller
  contact, approve the draft and check your inbox.
- [ ] **2.3 — (Optional) Gmail API mode.** Create an OAuth client in Google Cloud, then
  `uv run python scripts/gmail_auth.py client_secret.json` and set `EMAIL_MODE=gmail_api`.
- [ ] **Install Pango locally (or use Docker)** so WeasyPrint PDF tests run on your machine; they
  skipped on the build machine and run in CI.
