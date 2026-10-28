# Contributing to Escalate

Thanks for helping people get their money back. You don't need to write code to help:
country playbooks, translations and reviews of letter templates are just as valuable.

## Ways to help

- **Add or correct a country playbook.** Read [docs/CONTRIBUTING-PLAYBOOKS.md](docs/CONTRIBUTING-PLAYBOOKS.md)
  first. Every rule needs an official source.
- **Translate** the UI (`locales/<lang>.json`) or the letter templates (`templates/<cc>/<lang>/`).
- **Review templates** if you are a lawyer or work at a consumer-rights group. Tell us what is
  wrong; we record reviews in each playbook's changelog.
- **Fix bugs and pick up** a [good first issue](docs/good-first-issues.md).

## Development setup

```bash
uv sync
cp .env.example .env     # set FERNET_KEY; a model is only needed for evals and manual runs
make test                # must pass offline
make lint                # ruff, ruff format, mypy, playbook validator
```

Tesseract and Pango are needed for the OCR and PDF tests; without them those tests are skipped
locally and run in CI.

## Rules every change must keep

1. **No sending without approval.** Only `approve_message` sets `approved_at`; every channel's
   `send()` calls `require_approval()` first. The LLM never gets a tool that sends.
2. **Facts only.** Drafts may only use values from the case facts. Never invent amounts, dates,
   IDs, laws or addresses.
3. **$0 by default.** No paid service may be required; LLM access goes through the
   OpenAI-compatible client in `escalate/llm/`.
4. **Global.** Never hard-code a country, currency, language or region; use ISO codes.
5. **Privacy.** Never log card numbers, IBANs, national IDs, passwords or OTPs; never ask users
   for passwords, PINs or OTPs.
6. **Not legal advice.** Letters and exports keep the disclaimer.

## Pull requests

- Small, focused changes with tests. Unit tests use the fake LLM (`tests/fakes/fake_llm.py`) and
  must pass offline; use `freezegun` for anything time-based, never `sleep`.
- Type hints everywhere; Pydantic models for every LLM output.
- No new dependency without a one-line reason in the PR.
- Prompt changes (`escalate/llm/prompts/`) must come with an eval run (`make evals`) and the
  before/after numbers in `evals/report.md`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `test:`, `docs:`, `chore:`.

## Reporting security issues

Please don't open a public issue; see [SECURITY.md](SECURITY.md).
