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
| No message is sent without approval | Only `approve_message` sets `approved_at`. Every channel's `send()` starts with `require_approval()`, and so does the central `send_message()`. The LLM gets no tools at all. | `tests/test_gate.py`, `tests/test_security.py` (AST checks), `tests/test_graph.py::test_resuming_graph_with_approve_does_not_bypass_gate` |
| Drafts use case facts only | Every number, date and ID must come from the facts or the facts-only template; checked at drafting and again at approval (including the user's edits). | `tests/test_gate.py` |
| Polite tone | Code tone check blocks threats and insults before approval. | `tests/test_evals.py` |
| Evidence encrypted at rest | Fernet (`FERNET_KEY`), files named by SHA-256. | `tests/test_evidence.py` |
| No secrets or IDs in logs, drafts or stored text | `escalate/pii.py` masks card numbers (Luhn-checked), IBANs, Pakistan CNIC, India Aadhaar, US SSN, UK NI numbers and any typed password/PIN/OTP. It runs on event payloads, case descriptions, extracted evidence text, facts, drafts, edits, logged replies and every log record. | `tests/test_security.py` |
| Never ask for passwords, PINs or OTPs | The playbook validator rejects facts with such names; scam checklists must warn about them. | `tests/test_flows.py`, `tests/test_country_packs.py` |
| One-click deletion | `DELETE /cases/{id}` removes the DB rows, evidence files, scheduler jobs and the agent checkpoint. | `tests/test_security.py` |
| Abuse limits | New cases are rate-limited per client (`MAX_NEW_CASES_PER_HOUR`, default 10). A case needs at least one piece of evidence before it starts. Approval is refused when the same recipient already gets letters from 3 other cases in 30 days. | `tests/test_security.py` |
| Demo mode | `DEMO_MODE=true`: email is never really sent (approval is still required), uploads are capped at 5 MB, and cases are deleted after 24 hours. | `tests/test_security.py` |
| Cloud privacy warning | When `LLM_BASE_URL` is not local, the UI warns before you send real personal data. | `tests/test_llm.py`, `tests/test_ui.py` |

## Known limits (v0.1)

- **Single user, no login.** Run Escalate on your own machine or behind your own access
  control. Do not expose the API to the internet.
- The rate limiter is in memory (one API process).
- Masking is pattern-based. It will miss unusual ID formats; please report the ones it misses.
- Case text and facts in the SQLite database are masked but not encrypted; protect the
  `data/` folder (disk encryption).
- The Gmail API token is stored encrypted with the same `FERNET_KEY`. Keep `.env` private.
