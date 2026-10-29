# Security audit: Escalate v0.1

**Date:** 2026-10-29 · **Commit range:** up to the "Part 1–3" security work on `main` ·
**Status:** all High and Medium findings fixed; nothing open above Low.

This file records what was checked, how, what was found, and what is left. The short user-facing
version is [SECURITY.md](../SECURITY.md).

## Scope

- **Backend:** the FastAPI API (`escalate/`), agent, channels (email, post), evidence storage,
  OCR, PDF export, templates, settings, scheduler. Also the Streamlit dev UI client (`ui/`).
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
| DAST | OWASP ZAP 2.17.0 baseline (spider + passive scan) against a production web build and a `DEMO_MODE` API, both on throwaway data | Informational only (A20) |
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
| A2 | `cryptography` 46.0.3: 7 advisories (EC subgroup check, X.509 name constraints, PKCS7 oracle, buffer overflow on non-contiguous buffers, bundled OpenSSL) | Medium | Fixed (Linux, Docker, CI, Apple Silicon); Accepted (Intel macOS) | `cryptography>=50` everywhere except Intel macOS, where no newer wheel exists (see residual risks). Escalate only uses Fernet on `bytes`; none of the affected APIs are called | CI `security` job (pip-audit) |
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

**Open: none above Low.** Every finding is fixed, a false positive or accepted with a reason
above.

## The optional app lock

`APP_PASSCODE` (plain or an argon2 hash from `uv run python -m escalate.api.applock hash`)
puts every route except `/health` and `/auth/*` behind a session cookie (`HttpOnly`,
`SameSite=Strict`, `Secure` over https, 12 h, in memory). Five wrong passcodes per client (20
in total) per 15 minutes lock login. Unset means no change. It keeps out other people on the same
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
2. **Intel macOS keeps `cryptography` 46.0.3.** No newer wheel exists for that platform. The
   advisories affect X.509, PKCS7 and EC key loading, plus the bundled OpenSSL; Escalate uses
   only Fernet. Docker on Intel Macs uses the fixed Linux build.
3. **DNS time-of-check/time-of-use** on `LLM_BASE_URL`/`SMTP_HOST`: a hostname that changes
   its answer between the check and the connection is not fully covered.
4. **In-memory limits and sessions:** one API process; a restart resets rate limits and logs
   everyone out.
5. **Pattern-based PII masking** misses unusual ID formats.
6. **The database is not encrypted** (evidence files are). Use disk encryption.
7. **Prompt injection is mitigated, not solved:** the user's review of facts, recipient and
   letter is the final control. Evals with a real model are still a manual step.
8. **`style-src-attr 'unsafe-inline'`** in the web CSP: React and Radix set some styles as
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
