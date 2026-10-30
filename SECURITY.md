# Security

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private
"Report a vulnerability" button on this repository (Security → Advisories). Include the steps
to reproduce and the impact. You should get a reply within 7 days. Please give us a reasonable
time to fix the issue before you disclose it.

Escalate handles people's complaints, receipts and money disputes, so these count as security
issues: a way to send a message without the user's approval; a way to read another user's
evidence or case; secrets or identity numbers ending up in logs, drafts or exports; and
anything that lets Escalate be used to harass someone.

## How Escalate protects users

| Rule | How it is enforced | Test |
| --- | --- | --- |
| No message is sent without approval | Only `approve_message` sets `approved_at`. Every channel's `send()` starts with `require_approval()`, and so does the central `send_message()`. The LLM gets no tools at all. | `tests/test_gate.py`, `tests/security/test_safety_rules.py` (AST checks), `tests/test_graph.py::test_resuming_graph_with_approve_does_not_bypass_gate` |
| Drafts use case facts only | Every number, date and ID must come from the facts or the facts-only template; checked at drafting and again at approval (including the user's edits). | `tests/test_gate.py` |
| Polite tone | Code tone check blocks threats and insults before approval. | `tests/test_evals.py` |
| Evidence encrypted at rest | Fernet (`FERNET_KEY`), files named by SHA-256. | `tests/test_evidence.py` |
| No secrets or IDs in logs, drafts or stored text | `escalate/pii.py` masks: card numbers (13–19 digits, Luhn-checked; last 4 kept); IBANs; Pakistan CNIC; India Aadhaar; US SSN; UK National Insurance numbers; UK bank details written as "sort code 12-34-56" (last 2 kept) and "account / account number / account no 12345678" (8 digits, last 4 kept); and the value after password, passcode, passwd, PIN, OTP, one-time code/password, CVV, CVC, mot de passe, contraseña, senha or Passwort (with or without ":", "is", "est", "es", "é", "ist"), and after pw, pwd or pass only when followed by ":" or "=". It runs on event payloads, case descriptions, extracted evidence text, facts, drafts, edits, logged replies and every log record. | `tests/security/test_safety_rules.py` |
| Never ask for passwords, PINs or OTPs | The playbook validator rejects facts with such names; scam checklists must warn about them. | `tests/test_flows.py`, `tests/test_country_packs.py` |
| One-click deletion | `DELETE /cases/{id}` removes the DB rows, evidence files, scheduler jobs and the agent checkpoint. | `tests/security/test_safety_rules.py` |
| Abuse limits | New cases are rate-limited per client (`MAX_NEW_CASES_PER_HOUR`, default 10). A case needs at least one piece of evidence before it starts. Approval is refused when the same recipient already gets letters from 3 other cases in 30 days. | `tests/security/test_safety_rules.py` |
| Demo mode | `DEMO_MODE=true`: email is never really sent (approval is still required), uploads are capped at 5 MB, and cases are deleted after 24 hours. | `tests/security/test_safety_rules.py` |
| Cloud privacy warning | When `LLM_BASE_URL` is not local, the UI warns before you send real personal data. | `tests/test_llm.py`, `tests/test_ui.py` |

## Network and request hardening (after the independent review)

| Attack from the review | Defence | Regression test |
| --- | --- | --- |
| Cross-site form / `fetch(no-cors)` approves a letter, deletes all cases, uploads evidence, starts/retries cases, changes settings (CSRF) | Every POST/PUT/PATCH/DELETE needs an allowed `Origin` (`WEB_ORIGIN`, `UI_ORIGIN`) **and** `X-Escalate-Request: 1`. Approve and delete-all also need a JSON body `{"confirm": true}`. | `tests/security/test_review_findings.py` (CSRF section) |
| DNS rebinding (attacker domain resolving to 127.0.0.1) | `TrustedHostMiddleware`, `ALLOWED_HOSTS` (default `localhost,127.0.0.1`) | `test_unknown_host_header_is_refused` |
| Docker ports open to the whole network | Ports bind to 127.0.0.1; `make up ALLOW_LAN=true` opens them with a loud no-login warning | `tests/test_packaging.py` |
| SMTP without certificate checks (password readable by a network attacker) | `ssl.create_default_context()` for SMTP_SSL and STARTTLS | `tests/test_smtp_tls.py` (self-signed server refused) |
| SSRF through `LLM_BASE_URL` / `SMTP_HOST`, stored key sent to a new host | Link-local and cloud-metadata addresses always refused (also via DNS / IPv4-mapped IPv6); private/loopback only for `LOCAL_ENDPOINT_HOSTS`; checked on save and before connecting; changing a host clears its stored secret | `tests/security/test_review_findings.py` (SSRF section) |
| Prompt injection: planted recipient in evidence, crafted "resolved" reply | The user must confirm the exact recipient to approve (with a "recipient changed" warning); evidence never overwrites facts the user typed; a "resolved" verdict waits for the user's confirmation | `tests/security/test_review_findings.py` (prompt-injection section) |
| `/health` leaked configuration; guessable ids; plain-text secrets | `/health` is `{"ok": true}`; cases and messages use UUID public ids in the API; saved secrets are Fernet-encrypted | `tests/security/test_review_findings.py` |

## End-to-end audit (Part 1)

The full audit (scope, tools, every finding with its fix and test, residual risks and what
must change before a hosted version) is in [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).
In short:

| Area | Defence | Test |
| --- | --- | --- |
| Uploads | Magic bytes must match the extension; programs, scripts, archives and Office files refused; images over 40 MP and PDFs over 300 pages refused before OCR; random storage names; no paths in names | `tests/security/test_uploads.py` |
| PDF export | WeasyPrint only loads embedded `data:` images: no `file://`, no network | `tests/security/test_pdf_fetcher.py` |
| Templates (SSTI) | Sandboxed Jinja2; facts are variables, never template source | `tests/security/test_templates.py` |
| Abuse and size | Per-client limits on changes (120/min) and AI calls (20/min); 1 MB JSON cap; every request field bounded | `tests/security/test_limits.py` |
| Errors and logs | No stack traces or echoed input in responses; PII masking on uvicorn's loggers and tracebacks; API docs pages (CDN scripts) only with `API_DOCS=true` | `tests/security/test_limits.py`, `test_logging.py` |
| Routes | Every route is listed in a test; every state-changing route is behind the CSRF guard | `tests/security/test_routes.py` |
| Optional app lock | `APP_PASSCODE`: httpOnly SameSite=Strict session, argon2, rate-limited attempts | `tests/security/test_applock.py` |
| Web app | Nonce-based CSP (no `unsafe-inline`/`unsafe-eval` for scripts), HSTS, `X-Frame-Options: DENY`, nosniff, Referrer-Policy, Permissions-Policy; no raw HTML rendering (ESLint) | Playwright console guard, `npm run lint` |
| Supply chain | Actions pinned to SHAs, read-only token; Dependabot; gitleaks, pip-audit, bandit, semgrep, npm audit and ZAP in CI; pre-commit secret scanning (`make hooks`) | `.github/workflows/ci.yml` |

## Second independent review

| Attack | Defence | Regression test |
| --- | --- | --- |
| DNS rebinding through the Streamlit dev UI (N1) and its stored-passcode auto-login (N3) | Streamlit retired: not in compose or default targets; `make dev-ui-legacy` only, localhost-only with XSRF on; no stored passcode | `tests/security/test_legacy_ui.py` |
| SSRF via a 307 redirect from the LLM endpoint (N2) | The LLM client never follows redirects; the model test never returns a response body | `tests/security/test_llm_redirect.py` |
| Deleted cases recoverable from the database files (N4) | `secure_delete`, `VACUUM` and WAL truncation after delete-all; checkpoints and evidence removed | `tests/security/test_delete_all_scrub.py` |
| Broken access log (N5) | Masking keeps the log record's arguments | `tests/security/test_logging.py` |
| Parallel passcode guessing; owner lockout (N6) | Attempts reserved before verify; per-client exponential backoff | `tests/security/test_applock.py` |
| One upload freezes the API (N7) | Upload parsing and OCR off the event loop, with a timeout | `tests/security/test_upload_blocking.py` |
| Look-alike recipient addresses (N8) | Warning plus punycode on the confirmation | `tests/security/test_lookalike.py` |

Details: [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md#the-second-independent-review-8-findings--info).

## Why there's no login in v0.1

Escalate v0.1 runs on **your own computer, for you alone**: the API listens on `127.0.0.1`,
Docker publishes ports on `127.0.0.1`, and the browser talks to it on `localhost`. In that
setting, a login would mostly protect you from yourself, while adding password storage,
recovery and session bugs to a tool whose whole point is to be simple and free.

The real risks of a local, login-free API are **other websites** and **other devices**, and
those are handled without a login: the CSRF guard (allowed Origin + custom header), the Host
check against DNS rebinding, localhost-only ports, and the static public demo that has no API
at all.

What a login would add, an `APP_PASSCODE` adds when you want it (wrong passcodes back off per
client address; with `ALLOW_LAN=true` behind Docker all LAN devices may share one address, so
run `make unlock` on this machine to clear the backoff): set it in `.env` and the app
shows a lock screen (useful on a shared computer, or with `ALLOW_LAN=true`). It is not user
accounts: there is one passcode, one user, and one set of cases.

A hosted, multi-user version (Phase 2) needs real accounts and per-user isolation first; the
list is in [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md#must-dos-before-phase-2-hosted--multi-user).

## Known limits (v0.1)

- **Single user, no login by default** (see above; `APP_PASSCODE` adds a lock screen). Run
  Escalate on your own machine or behind your own access control. Do not expose the API to
  the internet. The CSRF, Host and port protections above
  defend against other *websites* and other *machines*, not against other programs running as
  you on the same computer.
- Endpoint checks resolve DNS when settings are saved and again before connecting; a hostname
  that changes its DNS answer between that check and the connection is not fully covered.
- Rate limits and app-lock sessions are in memory (one API process; a restart resets them).
- `WEB_ORIGIN` (and `UI_ORIGIN`, empty by default) are trusted completely: whatever serves
  pages on those local ports can change cases and approve letters. Don't run other web servers
  there.
- Masking is pattern-based. It will miss unusual ID formats; please report the ones it misses.
- Case text and facts in the SQLite database are masked but not encrypted; protect the
  `data/` folder (disk encryption).
- The Gmail API token is stored encrypted with the same `FERNET_KEY`. Keep `.env` private.
