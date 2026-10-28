# Decisions

Defaults chosen during the autonomous build, with the reason for each.

## Tooling
- **Flat package layout** (`escalate/` at the repo root, not `src/`), matching CLAUDE.md. Built with
  `uv_build` (`module-root = ""`) so `uv sync` installs the package editable and `ui/app.py` can
  import it.
- **`cryptography` pinned to 46.0.3 on Intel macOS only.** Newer releases ship no x86_64 macOS
  wheel and fail to build without OpenSSL headers. All other platforms (Linux, Docker, CI, Apple
  Silicon) get the current release via a platform marker.
- **`python-multipart`** added: FastAPI needs it for the multipart evidence upload endpoint.
- **`types-PyYAML`, `types-jsonschema`** added as dev deps so mypy can check YAML/schema code.
- CI also runs `ruff format --check` (listed in CLAUDE.md's lint command) and installs Pango so
  WeasyPrint can render PDFs.

## Database (task 1.2)
- `Case.country` and `Case.currency` are **nullable**: a case is created from free text before
  classification, and CLAUDE.md forbids country/currency defaults. `classify` fills them.
- Extra columns beyond section 5: `Case.description` (user's own words), `Evidence.filename`,
  `Evidence.ocr_confidence`, `Evidence.needs_review` (task 1.4), `Message.rejection_reason`,
  `Message.external_id` (Gmail message id), `Message.created_at`. Message status adds `rejected`.
- `amount` is `Decimal` (not float) to avoid rounding money.
- Foreign keys use `ON DELETE CASCADE` and SQLite `PRAGMA foreign_keys=ON`, so deletes cascade
  both via the ORM and at SQL level.
- Timestamps are naive UTC via `escalate.db.models.utcnow()` (works with freezegun).
