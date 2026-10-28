# Manual steps

Things the autonomous build could not do because they need you, a real account, or hardware
that was not available. Each item names the task it came from.

- [ ] **1.3 — Pull a local model and ping it.** No Ollama model was pulled during the build.
  Run `ollama pull <model>` (an open 7–8B instruct model), set `MODEL_SMART`/`MODEL_FAST` in
  `.env`, then `uv run python scripts/llm_ping.py` and confirm you get an answer.
- [ ] **1.4 — Install Tesseract locally.** It was not installed on the build machine, so
  `test_real_ocr_reads_fixture_receipt` skipped locally (CI installs Tesseract and runs it).
  Install `tesseract` + language packs (e.g. `urd`), then run `uv run pytest tests/test_evidence.py`.
