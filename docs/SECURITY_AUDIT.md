# Security audit: Escalate v0.1

**Date:** 2026-10-29, updated after the second (N1–N8) and third (M1, L1–L4, I1–I2)
independent reviews · **Commit range:** up to the third-review fixes on `main` ·
**Status:** all High and Medium findings fixed; nothing open above Low.

This file records what was checked, how, what was found, and what is left. The short user-facing
version is [SECURITY.md](../SECURITY.md).

## Scope

- **Backend:** the FastAPI API (`escalate/`), agent, channels (email, post), evidence storage,
  OCR, PDF export, templates, settings, scheduler. The Streamlit dev UI (`ui/`) was in scope for the second review and is now retired
  (opt-in `make dev-ui-legacy` only, unsupported).
- **Web app:** the Next.js app (`web/`), in both builds: self-hosted, and the static live demo.
- **Supply chain:** Python and npm dependencies, GitHub Actions, Docker images.
- **Repository:** the full git history (the repository is public).
- **Out of scope:** the user's machine, OS and browser; the LLM provider; email providers.
  Hosted multi-user deployments (Phase 2) are a different threat model (see the end).

**Threat model (v0.1).** Escalate is single-user and self-hosted on `localhost`, with no login
(see [Why there's no login in v0.1](../SECURITY.md#why-theres-no-login-in-v01)). The attackers
considered are: a website the user visits (CSRF, DNS rebinding); another device on the same
network; a malicious company planting text in evidence or replies (prompt injection); a
malicious file upload; and a compromised dependency or CI action. Other programs running as the
same user on the same computer are not in scope.

## Method

| Area | Tool / method | Result |
| --- | --- | --- |
| Secrets in git history | gitleaks 8.30.1, `gitleaks git` over all 49 commits | 2 false positives (A1); no secrets |
| Secrets in the working tree and bundles | gitleaks `dir`; `web/scripts/scan-bundle.mjs` | none in tracked files or browser bundles |
| Committed data files | `git log --diff-filter=A` for `.env`, `*.db`, `data/`, `secrets/`, `settings.json`; screenshots inspected | none; screenshots use throwaway demo data only |
| Python dependencies | pip-audit (OSV + PyPI advisories) on `uv.lock` | 7 advisories in `cryptography` 46.0.3 (A2) |
| npm dependencies | `npm audit` | 0 vulnerabilities |
| Python SAST | bandit 1.9.4; semgrep `p/python`, `p/fastapi`, `p/flask`, `p/secrets` | A3–A5 |
| Web SAST | semgrep `p/typescript`, `p/react`, `p/nextjs`; ESLint with `eslint-plugin-security` and `eslint-plugin-no-unsanitized` | A6; no `dangerouslySetInnerHTML`, `eval` or HTML sinks |
| Manual review | every route (inventory test), uploads, PDF, templates, logging, errors, prompt-injection paths | A7–A19 |
| DAST | OWASP ZAP 2.17.0 baseline (spider + passive scan) against a production web build and a `DEMO_MODE` API, both on throwaway data | A22 (fixed); then Informational only (A20) |
| Regression | `tests/security/` (pytest) and Playwright (`demo`, `guard`) | all pass; run in CI on every push |

## Findings

Severity is for v0.1's threat model. **Status:** Fixed, Accepted (with reason) or
False positive.

### The independent review (8 findings)

All eight were fixed in the "Priority 0" commits. The reviewer's reproduction commands were
replayed against a throwaway API and now fail (403/400/409/422 as listed).

| # | Finding | Severity | Status | Fix | Regression test |
| --- | --- | --- | --- | --- | --- |
| R1 | Any website could approve and send letters (CSRF) | Critical | Fixed | Allowed `Origin` **and** `X-Escalate-Request: 1` on every POST/PUT/PATCH/DELETE; approve needs `{"confirm": true, "recipient": …}` | `tests/security/test_review_findings.py::test_cross_site_form_cannot_approve_and_send`, `test_routes.py::test_every_state_changing_route_is_behind_the_csrf_guard` |
| R2 | Other one-click actions from any website (delete-all, start, retry, seed, settings) | High | Fixed | Same guard; delete-all needs a JSON confirmation | `test_review_findings.py::test_every_state_change_needs_origin_and_header`, `test_delete_all_needs_a_confirmation_body` |
| R3 | DNS rebinding let a website read everything | High | Fixed | `TrustedHostMiddleware` with `ALLOWED_HOSTS` | `test_review_findings.py::test_unknown_host_header_is_refused` |
| R4 | Docker Compose published every port on the LAN | High | Fixed | Ports bind `127.0.0.1`; `make up ALLOW_LAN=true` opens them with a no-login warning | `tests/test_packaging.py` |
| R5 | SMTP did not verify the server certificate | Medium | Fixed | `ssl.create_default_context()` for SMTP_SSL and STARTTLS | `tests/test_smtp_tls.py` |
| R6 | Settings could point the API at internal addresses and send the API key there (SSRF) | Medium | Fixed | Metadata and link-local always refused (also via DNS and IPv4-mapped IPv6); private hosts only from `LOCAL_ENDPOINT_HOSTS`; checked on save and before connecting; changing a host clears its stored secret | `test_review_findings.py` (SSRF section) |
| R7 | Prompt injection through evidence or replies | Medium–Low | Fixed | User confirms the exact recipient (with a "recipient changed" warning); evidence never overrides facts the user typed; "resolved" waits for the user; see also A9 | `test_review_findings.py` (prompt-injection section), `tests/security/test_injection.py` |
| R8 | `/health` leaked configuration; sequential ids; secrets in plain text in `settings.json` | Low | Fixed | `/health` is `{"ok": true}`; UUID public ids; Fernet-encrypted saved secrets | `test_review_findings.py::test_health_exposes_nothing`, `test_api_ids_are_unguessable`, `test_saved_secrets_are_encrypted_at_rest` |

### This audit

| # | Finding | Severity | Status | Fix | Test |
| --- | --- | --- | --- | --- | --- |
| A1 | gitleaks `generic-api-key` in `.env.example` and `docs/BUILD_PLAN.md` | Info | False positive | The value is empty (`SMTP_APP_PASSWORD=`); the rule matched the next line's key name. Listed in `.gitleaksignore` by fingerprint. **Nothing to rotate.** | CI `security` job (gitleaks) |
| A2 | `cryptography` 46.0.3: 7 advisories (EC subgroup check, X.509 name constraints and chain building, PKCS7 oracle, buffer overflow on non-contiguous buffers, bundled OpenSSL) | Medium | Fixed (Linux, Docker, CI, Apple Silicon: 50.x); Fixed except 3 (Intel macOS: 48.0.1) | Intel macOS now gets 48.0.1 (its universal2 wheel; 49+ ship arm64 only), which fixes 4 of the 7. Still open there, accepted: PYSEC-2026-3554 and PYSEC-2026-3553 (X.509 name constraints / duplicate self-signed chain building, fixed in 49) and PYSEC-2026-3552 (PKCS7 decryption oracle, fixed in 50). Escalate never verifies certificate chains or decrypts PKCS7 with `cryptography` (only Fernet; TLS uses Python's `ssl`) | CI `security` job (pip-audit, those 3 ids ignored explicitly); `tests/test_packaging.py::test_locked_cryptography_is_at_least_48_0_1` |
| A3 | Jinja2 `autoescape=False` (bandit B701) | Low | Fixed | `SandboxedEnvironment` for letters and the case file. Letters stay unescaped on purpose (Markdown sent as email text; escaping would put `&amp;` in a letter); they are HTML-escaped when turned into a PDF. Facts are only ever passed as variables | `tests/security/test_templates.py` (`{{7*7}}`, `{{config}}`, `__class__`, `__globals__`) |
| A4 | bandit B104 (`"0.0.0.0"`), B610 (`.update(extra(...))`), B112 (cookie parse `continue`) | Info | False positive | Annotated with `# nosec` and a reason; B101 (assert) skipped in `pyproject.toml` with a reason | CI `security` job (bandit) |
| A5 | semgrep `avoid-sqlalchemy-text` in the public-id migration | Info | False positive | Table names come from a constant tuple; values are bound parameters. Annotated | CI `security` job (semgrep) |
| A6 | ESLint security: `detect-object-injection` (13), fs/RegExp in build scripts (10) | Info | Justified | Object-injection reads are keyed by TypeScript unions or API enums, never written by user key; fs rules off for build scripts and tests only. Lint fails on any warning | `npm run lint` |
| A7 | Uploads trusted the extension: executables, archives or a mislabelled file could be stored; no image-size limit (decompression bomb); files named by content hash | Medium | Fixed | Magic bytes must match the extension; programs, scripts, archives and OLE files refused (415); images over 40 MP and PDFs over 300 pages refused before OCR; random storage names; display names stripped of paths and control characters; OCR caps pages and text | `tests/security/test_uploads.py` |
| A8 | The PDF renderer (WeasyPrint) could fetch `file://` and network URLs | Medium | Fixed | A fetcher that only loads `data:` URIs, no redirects | `tests/security/test_pdf_fetcher.py` (local HTTP spy sees no request; `/etc/passwd` not embedded) |
| A9 | A fact citing evidence that doesn't exist was kept (with the citation dropped) | Medium | Fixed | Such a fact is only kept if the user wrote that value themselves | `tests/security/test_injection.py`, `tests/test_intake.py` |
| A10 | No rate limit on writes or AI calls; no request body cap | Medium | Fixed | Per-client limits (120 writes/min, 20 AI calls/min), 1 MB JSON cap (uploads: `MAX_UPLOAD_MB`), bounds on every request field and query | `tests/security/test_limits.py` |
| A11 | uvicorn's own loggers and tracebacks were not PII-masked | Medium | Fixed | The masking filter covers `uvicorn`, `uvicorn.error`, `uvicorn.access` and their handlers, and exception text | `tests/security/test_logging.py` |
| A12 | No security headers on the API; no CSP on the web app | Medium | Fixed | API: nosniff, `X-Frame-Options: DENY`, no-referrer, `no-store`, `default-src 'none'` CSP. Web: per-request nonce CSP (`'strict-dynamic'`, no `unsafe-inline`/`unsafe-eval` for scripts in production), HSTS, DENY, nosniff, Referrer-Policy, Permissions-Policy, COOP | `test_limits.py::test_api_responses_carry_security_headers`; Playwright console guard fails on any CSP violation |
| A13 | 422 responses echoed the submitted input (e.g. an API key) | Low | Fixed | Validation errors return location, message and type only | `test_limits.py::test_validation_errors_do_not_echo_input` |
| A14 | Unexpected errors could return internal messages | Low | Fixed | A generic 500 with an error id; the traceback goes to the (masked) console | `test_limits.py::test_unexpected_errors_are_generic` |
| A15 | `/checklist?country=` was joined into a file path | Low | Fixed | Only ISO 3166-1 alpha-2 codes are used | `test_limits.py::test_checklist_country_is_never_a_path` |
| A16 | Proof of delivery could be evidence from another case | Low | Fixed | Must belong to the same case | `tests/security/test_case_scoping.py` |
| A17 | The printable PDF filename used the internal integer id | Low | Fixed | Uses the public UUID | covered by `test_review_findings.py::test_api_ids_are_unguessable` |
| A18 | GitHub Actions pinned to tags; default token permissions | Medium | Fixed | Actions pinned to commit SHAs; `permissions: contents: read`; `persist-credentials: false`; downloaded tools checked by SHA-256; Dependabot for uv, npm, Actions and Docker | `.github/workflows/ci.yml` |
| A19 | Tests that forgot the database fixture used `./escalate.db` | Low | Fixed | `tests/conftest.py` points `DATABASE_URL` at an in-memory DB | the whole suite |
| A20 | ZAP: "Information Disclosure – Suspicious Comments" (the word "user" in minified JavaScript) | Info | Accepted | Framework code, no secrets | CI `zap` job (fails on Medium or higher) |
| A21 | Settings → Delete all showed "All cases deleted" even when the request failed | Low | Fixed | Success is shown only after the API confirms | `web/e2e/demo.spec.ts` |
| A22 | FastAPI's `/docs` (Swagger UI) loads scripts from a CDN without Subresource Integrity, and the page had no CSP (ZAP 90003, 10038) | Medium | Fixed | `/docs` and `/redoc` are off unless `API_DOCS=true` (`make api` sets it for development); `/openapi.json` stays | `tests/security/test_limits.py::test_api_docs_are_opt_in`; CI `zap` job |

### The second independent review (8 findings + INFO)

Each fix has a regression test that replays the reported attack; every one of those tests
fails on the code before the fix.

| # | Finding | Severity | Status | Fix | Regression test |
| --- | --- | --- | --- | --- | --- |
| N1 | The Streamlit dev UI answered any `Host` header: a DNS-rebinding page could drive it, and through it the API (it ran server-side with a trusted origin) | High | Fixed | Retired: removed from docker-compose and the default make targets; opt-in `make dev-ui-legacy` with an UNSUPPORTED warning and `.streamlit/config.toml` (bind 127.0.0.1, `server.allowedHosts` localhost/127.0.0.1, XSRF protection on). `UI_ORIGIN` now defaults to empty, so the API trusts only the web app. Docs point to the web app only | `tests/security/test_legacy_ui.py` (compose has no Streamlit service; 8501 origin refused by default) |
| N2 | SSRF via redirect: an allowed LLM endpoint answered 307 to an internal address; the SDK followed it with the API key, and `/settings/llm-test` returned the internal response body | Medium | Fixed | The OpenAI client uses `DefaultHttpx2Client(follow_redirects=False)`; llm-test reports only "the endpoint answered HTTP <code>" / "connection failed" / our own settings messages | `tests/security/test_llm_redirect.py` (the reviewer's 307 → internal-server repro: no hit, no key, no body) |
| N3 | The Streamlit UI logged in automatically with a stored `UI_PASSCODE`/`APP_PASSCODE` through one module-level cookie jar shared by every browser session | Medium | Fixed | Removed with N1: no stored passcode, no shared cookies | `test_legacy_ui.py::test_legacy_ui_client_has_no_auto_login_or_shared_cookies` |
| N4 | After delete-all, `strings` on the database, its WAL and the checkpoint file still showed the deleted cases | Low | Fixed | `PRAGMA secure_delete=ON` on both SQLite files; delete-all clears every LangGraph checkpoint, `VACUUM`s both files, truncates their WALs and removes leftover evidence folders | `tests/security/test_delete_all_scrub.py` (no demo-case text in any file on disk) |
| N5 | The PII log filter set `record.args=None`, which broke uvicorn's access log formatter | Low | Fixed | Masks the message template and each argument, keeping their shape | `tests/security/test_logging.py::test_uvicorn_access_log_still_formats_and_is_masked` |
| N6 | Passcode limiter race (parallel guesses all verified) and a global lockout the owner couldn't escape | Low | Fixed | Each attempt is reserved under a lock before argon2 runs; per client 5 free attempts, then one at a time with exponential backoff (30 s doubling, 15 min cap); no global lockout | `tests/security/test_applock.py` (40 parallel wrong logins → ≤5 verified; backoff 30 → 60 s; owner unaffected) |
| N7 | OCR and PDF parsing ran on the event loop: one large upload froze every request | Low | Fixed | Upload checks, extraction and encryption run in worker threads; extraction is abandoned after `OCR_TIMEOUT_S` (Tesseract gets the same timeout) and the file is marked for review | `tests/security/test_upload_blocking.py` (`/health` answers during OCR; timeout path) |
| N8 | Look-alike recipients (e.g. Cyrillic "а") looked identical on the confirmation screen | Low | Fixed | Non-ASCII addresses get a warning ("mixes alphabets" / "non-English letters") and the punycode form next to the confirmation checkbox | `tests/security/test_lookalike.py` |
| INFO | `/openapi.json` served the full route map in production | Info | Fixed | Follows `API_DOCS` like `/docs`; `python -m escalate.api.schema` exports it for tools (ZAP) | `test_limits.py::test_api_docs_are_opt_in`, `test_info_items.py` |
| INFO | A saved hostname that doesn't resolve gave no feedback | Info | Fixed | Saved with a warning shown on the settings page | `test_info_items.py` |
| INFO | `WEB_ORIGIN`/`UI_ORIGIN` trust whatever runs on those local ports | Info | Documented | `.env.example` and SECURITY.md say so; `UI_ORIGIN` is empty by default (N1) | — |

### The third independent review (no Critical/High; verdict "Ready")

All fixed, one commit each; each regression test fails on the code before its fix.

| # | Finding | Severity | Status | Fix | Regression test |
| --- | --- | --- | --- | --- | --- |
| M1 | Parallel approves: the "waiting for approval?" check ran outside the lock and the resume wasn't tied to the approval. 4 parallel `POST /messages/{id}/approve` gave 4 approval events and 1 send, then the extra resumes were judged "no reply" and the ladder jumped to the final notice | Medium | Fixed | A per-case lock makes check, approval and resume one step for every runner entry point; the resume carries the approved message id and is refused (409) unless that draft is the one pending; `approve_message` refuses a non-draft. Web: the confirm button is guarded until the response | `tests/security/test_parallel_approve.py` (1×200 + 3×409, one approval, one send, `waiting_reply`, no `reply_judged`) |
| L1 | Ollama's 11434 published on the host (on the LAN with `ALLOW_LAN`); image unpinned | Low | Fixed | No published port (the API uses the compose network; `make pull` uses `exec`); `ollama/ollama:0.40.13`, updated by Dependabot's docker-compose ecosystem | `tests/test_packaging.py::test_ollama_is_not_published_and_is_pinned` |
| L2 | Intel macOS on `cryptography` 46.0.3 | Low | Fixed | 48.0.1 (universal2 wheel) on Intel macOS, 50.x elsewhere; only PYSEC-2026-3552/3553/3554 remain there, accepted (see A2) | `tests/test_packaging.py::test_locked_cryptography_is_at_least_48_0_1`; CI pip-audit |
| L3 | PII masking missed `pw:`, `pass:`, `passwd:`, `pwd:`, mot de passe, contraseña, senha, Passwort and UK sort code / account details | Low | Fixed | Added (short forms only with `:`/`=`); SECURITY.md lists exactly what is masked | `tests/security/test_safety_rules.py::test_mask_pii` (16 new cases) |
| L4 | Passcode backoff behind Docker NAT: every LAN device can share one address, so a guesser delays the owner | Low | Fixed | `make unlock` (local) clears the backoff; documented; stale "20 in total" text removed | `tests/security/test_applock.py::test_owner_can_clear_the_backoff_locally` |
| I1 | Anti-harassment limit compared recipients literally and reset when cases were deleted | Info | Fixed | Normalised recipients (lowercase, no `+tag`, Gmail dots); a keyed-hash record per approval (no PII, no FK) survives deletion | `tests/security/test_recipient_limit.py` |
| I2 | `.dockerignore` missed WAL/journal/`.env.*` files; API container ran as root | Info | Fixed | Patterns added; non-root `escalate` user (uid 1000); CI checks `id -u` ≠ 0 | `tests/test_packaging.py::test_api_image_runs_as_non_root_and_ignores_local_data` |

**Open: none above Low.** Every finding is fixed, a false positive or accepted with a reason
above.

## The optional app lock

`APP_PASSCODE` (plain or an argon2 hash from `uv run python -m escalate.api.applock hash`)
puts every route except `/health` and `/auth/*` behind a session cookie (`HttpOnly`,
`SameSite=Strict`, `Secure` over https, 12 h, in memory). Each attempt is reserved before the
argon2 check; per client address, 5 free attempts, then one at a time with exponential backoff
(30 s, doubling, 15 min cap); there is no global lockout. Behind Docker's NAT (`ALLOW_LAN=true`
with Docker) every LAN device can reach the API from the same address, so one device's wrong
guesses delay the others: the owner clears the backoff with `make unlock` on the machine
running Escalate. Unset means no change. It keeps out other people on the same
computer or network. It is not user accounts. Tests: `tests/security/test_applock.py` and
`test_routes.py`, which checks that every non-allow-listed route answers 401 when locked.

## The public live demo

The Vercel demo is a static build (`NEXT_PUBLIC_DEMO_STATIC=true`) with bundled sample data
and no API: no request can carry user data anywhere. CI proves it:
- The Playwright `demo` project fails if any request leaves the app's own origin; it runs with
  no API started.
- The CSP's `connect-src` is `'self'` only.
- `scan-bundle.mjs --demo` and gitleaks find no secrets, local or internal URLs in the bundle.
- Self-hosted builds are checked not to carry the demo data.

See [DEPLOY_DEMO.md](DEPLOY_DEMO.md).

## Residual risks (accepted for v0.1)

1. **No login by default.** Anyone who can run programs as you, or reach the API if you set
   `ALLOW_LAN=true`, can use it. `APP_PASSCODE` narrows this; it is not multi-user security.
2. **Intel macOS uses `cryptography` 48.0.1** (the last release with a universal2 wheel). Three
   advisories stay open there: PYSEC-2026-3554 and PYSEC-2026-3553 (X.509 verification, fixed
   in 49) and PYSEC-2026-3552 (PKCS7 decryption, fixed in 50). Escalate calls none of those
   APIs; it uses only Fernet. Docker on Intel Macs uses the fixed Linux build (50.x).
3. **DNS time-of-check/time-of-use** on `LLM_BASE_URL`/`SMTP_HOST`: a hostname that changes
   its answer between the check and the connection is not fully covered.
4. **In-memory limits and sessions:** one API process; a restart resets rate limits and logs
   everyone out.
5. **Pattern-based PII masking** misses unusual ID formats.
6. **The database is not encrypted** (evidence files are). Use disk encryption.
7. **Prompt injection is mitigated, not solved:** the user's review of facts, recipient and
   letter is the final control. Evals with a real model are still a manual step.
8. **Trusted local origins:** any program serving pages on `WEB_ORIGIN` (default
   `http://localhost:3000`) or `UI_ORIGIN` can make state-changing calls. Don't run other web
   servers on those ports.
9. **Abandoned OCR threads** keep running until Tesseract's own timeout (`OCR_TIMEOUT_S`)
   stops them; PDF parsing has no internal timeout, only the page cap.
10. **`style-src-attr 'unsafe-inline'`** in the web CSP: React and Radix set some styles as
   attributes. Style attributes cannot run script.

## Must-dos before Phase 2 (hosted / multi-user)

- **Real authentication:** accounts, password hashing (argon2), MFA, session management with
  rotation and revocation, CSRF tokens bound to sessions, account recovery.
- **Per-user isolation:** every query scoped by user (row-level checks or separate databases),
  per-user evidence keys, authorization tests for every route (extend `test_routes.py`).
- **Hosted secrets:** a secret manager or KMS for `FERNET_KEY` and provider keys, key rotation,
  no secrets in environment files on disk.
- **Shared rate limits and sessions** (Redis or the database), across processes.
- **Encryption at rest** for the database, backups, and audit logs of every approval and send.
- **Abuse controls** for a public service: sign-up limits, sending quotas, harassment review.
- **Legal and privacy:** data processing terms, retention and deletion, breach process.
- **A fresh external penetration test** of the hosted system.

## How to re-run

```bash
make security        # gitleaks, pip-audit, bandit, semgrep, npm audit, tests/security
make demo-build      # demo bundle + scan
make zap ZAP=/path/to/zap.sh WEB_URL=… API_URL=…   # against throwaway DEMO_MODE instances only
```
