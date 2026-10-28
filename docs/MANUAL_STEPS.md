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
- [ ] **2.6 — Run the LED case by hand in the browser and record a rough screen capture.**
  Start the API (`uv run uvicorn escalate.api.main:app --reload`) and the UI
  (`uv run streamlit run ui/app.py`) with a local model configured. The build only booted both
  servers headless and checked `/health`; no model was available to draft letters.
- [ ] **3.1 / 4.2 — Lawyer or consumer-rights review of the Pakistan templates** (`templates/pk/en`
  and `templates/pk/ur`): seller demand, platform escalation, 15-day legal notice, consumer
  court complaint, condonation of delay. Record the review in the playbook changelog. Also
  resolve the `TODO(verify …)` list at the top of `playbooks/pk/ecommerce/refund_refused.yaml`
  (Act names per province, filing limit, notice requirement).
- [ ] **3.1 — Native Urdu speaker review** of `templates/pk/ur/*` and the Urdu disclaimer line.
- [ ] **3.3 — Verify the India, UK and US packs** (and the PK scam checklist) from official
  government sites: resolve every `TODO(verify)` in `playbooks/{in,gb,us}/**` and
  `playbooks/{pk,in,gb,us}/scam_checklist.yaml` (authority names, URLs, helpline numbers, time
  limits), or open issues labelled `country:<cc>` and `good first issue` for contributors.
- [ ] **3.4 — Complete `locales/ur.json`** with a native speaker (only ~20 strings are
  translated; the rest fall back to English).
- [ ] **3.5 — Export the LED case PDF and click through every screen by hand** with a real
  model. Locally the PDF render was not possible (no Pango); CI runs the PDF test.
- [ ] **4.1 — Reach the eval targets with a real local model** and name it in the README.
  Targets: extraction ≥ 95%, classification ≥ 95%, 0 unsupported facts, 0 tone flags, reply
  judge ≥ 90%. Run `uv run python -m evals.run --suite all`, add the numbers to the History
  table in `evals/report.md`, and fix misses (prompt wording, few-shot examples, code checks)
  without lowering targets. The build applied model-independent fixes only.
- [ ] **4.3 — Fresh-install test with Docker.** Docker was not available on the build machine.
  On a machine with Docker: fresh clone, `make setup && make up`, open http://localhost:3000 (web app; Streamlit dev UI on :8501)
  and open a case. (CI builds the image and smoke-tests OCR and PDF rendering inside it.)
  `make setup` pulls `llama3.1:8b` by default; pass `MODEL=<name>` to choose another.
- [ ] **4.4 — Record the demo GIF** (30–45 s: broken-LED photo → draft → approve → timeline jumps
  to the legal notice → PDF), save it as `docs/demo.gif`, and uncomment the image line near the
  top of `README.md`.
- [ ] **4.4 — Open the 10 issues** in `docs/good-first-issues.md` on GitHub, create the labels
  (`good first issue`, `playbook`, `country:pk`, …) and set the repo topics (`ai-agent`,
  `consumer-rights`, `langgraph`, `llm`, `legal-tech`, `i18n`, `self-hosted`). `gh` was not
  available during the build.
- [ ] **4.5 — Tag v0.1.0, publish the GitHub release and open the good-first issues.** Release
  notes are in `docs/releases/v0.1.0.md`. Commands:
  ```bash
  git pull --ff-only
  git tag -a v0.1.0 -m "Escalate v0.1.0"
  git push origin v0.1.0
  # then on GitHub: Releases → Draft a new release → tag v0.1.0 → paste docs/releases/v0.1.0.md
  # or, with the GitHub CLI: gh release create v0.1.0 --title "Escalate v0.1.0" --notes-file docs/releases/v0.1.0.md
  ```
- [ ] **After launch** (from the plan): launch posts, optional hosted demo in `DEMO_MODE`
  (check current free-tier terms first), daily issue triage for two weeks.
- [ ] **Git identity:** commits in this repo are authored as "Your Name <you@example.com>" (the
  local git config). Set yours with `git config user.name` / `user.email` before tagging if you
  want the release attributed to you.

## Web frontend (web/)
- [ ] **Translate the UI.** `web/messages/{es,fr,pt,ar,hi,ur,id}.json` ship empty ("help
  translate" note), so those languages show English. Native speakers: copy keys from `en.json`.
- [ ] **Try the web app with a real model.** The build machine had no model, so drafting,
  extraction and reply judging were only exercised through the scripted demo data and stubbed
  screenshots (the reply verdict and missing-facts screenshots use stubbed API answers). Run a
  real case end to end in the browser.
- [ ] **Check accessibility by hand** with a screen reader and keyboard only, and run an automated
  contrast check (e.g. axe) in both themes. Colours were chosen for 4.5:1 but not machine-verified.
- [ ] **Verify the SMTP presets** in Settings (Gmail, Outlook.com, Yahoo, iCloud hosts and ports)
  against each provider's current help page before relying on them.
