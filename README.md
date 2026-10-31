# Escalate

[![Live demo](https://img.shields.io/badge/live%20demo-try%20it-d7f36b?style=flat-square)](https://escalate-chi.vercel.app)
[![CI](https://github.com/zainismail-dev/escalate/actions/workflows/ci.yml/badge.svg)](https://github.com/zainismail-dev/escalate/actions/workflows/ci.yml)

**The AI agent that fights for your refund, so you don't give up.**

Escalate takes your complaint and your evidence (a refund refused, a subscription that won't
cancel, a scam) and runs it up the ladder: a written demand, a final notice, the consumer
authority, then consumer court. It drafts every letter, tracks deadlines and follows up when the
company goes quiet. **You approve every message before it is sent.** It runs on your own
computer, with a free local AI model.

<!-- Demo GIF: record it and save as docs/demo.gif, then uncomment the next line.
![Escalate demo: photo of a broken LED, a draft appears, approve, the timeline jumps to the legal notice, PDF case file](docs/demo.gif)
-->
> 🎬 Demo GIF coming soon (`docs/demo.gif`).

> ⚖️ Escalate is a self-help tool, **not legal advice**. Check the rules in your country.

**Try it first:** the [live demo](https://escalate-chi.vercel.app) runs in your browser with
sample cases. Nothing is saved or sent, and no data leaves the page
([how it works](docs/DEPLOY_DEMO.md)).

## Why it exists

A family member bought an LED TV that broke within days. They returned it, and for eight months
the shop answered every message with "we'll replace it when the company approves the claim".
Most people give up at that point: they don't know the next step, the deadlines, or how to write
a legal notice. Escalate knows the ladder, writes the letters, and keeps the pressure on until
the case is resolved or ready for court.

## Quick start

You need [Docker](https://docs.docker.com/get-docker/) and about 8–16 GB of RAM for the local model.

```bash
git clone https://github.com/zainismail-dev/escalate.git && cd escalate
make setup     # creates .env (with an encryption key), builds images, pulls a local model
make up        # then open http://localhost:3000
make demo-data # optional: four fictional demo cases (PK, IN, GB, US); nothing is sent
```

`make setup` pulls `llama3.1:8b` by default (`make setup MODEL=<name>` for another). No model has
been evaluated as "recommended" yet: see [evals/report.md](evals/report.md).

Without `make`: `cp .env.example .env`, set `FERNET_KEY` and `MODEL_SMART`, then
`docker compose up`.

<details>
<summary>Run without Docker (for development)</summary>

```bash
uv sync
cp .env.example .env        # set FERNET_KEY, MODEL_SMART, MODEL_FAST
make api                                          # API on :8000
make web-install && make web-dev                  # web app on http://localhost:3000
```

You also need Node.js 20.9+ for the web app, and Tesseract (OCR) and Pango (PDF export) on your
system.
</details>

## Screenshots

The web app (`web/`, Next.js) is the interface. (The old Streamlit dev UI is retired:
unsupported, opt-in only with `make dev-ui-legacy`.)
All screenshots use the fictional demo cases. Full set: [docs/screenshots/](docs/screenshots/).

| | |
| --- | --- |
| ![Landing page with the escalation ladder](docs/screenshots/01-landing.png) | ![My cases: needs-you-today cards, filters and mini ladders](docs/screenshots/02-my-cases.png) |
| **Landing** | **My cases** |
| ![Case dashboard: ladder, next move and the agent's reasons](docs/screenshots/08-case-dashboard.png) | ![Review draft: verified facts highlighted, safety checks, decision card](docs/screenshots/09-review-draft.png) |
| **Case dashboard** | **Review draft** |
| ![A blank to fill keeps Approve disabled](docs/screenshots/11-review-blank-to-fill.png) | ![Mobile: review draft](docs/screenshots/21-mobile-review.png) |
| **Blanks block approval** | **Mobile** |
| ![Draft blocked by the fact check: wrong vs. evidence value](docs/screenshots/12-state-fact-check-blocked.png) | ![Scam urgent checklist](docs/screenshots/13-scam-urgent-checklist.png) |
| **Blocked by the fact check** | **Scam: urgent checklist** |
| ![New case wizard: where you are](docs/screenshots/03-new-case-where.png) | ![Missing facts with "why we ask"](docs/screenshots/07-missing-facts.png) |
| **New case wizard** | **Missing facts** |
| ![Reply verdict with offered, by when and condition](docs/screenshots/15-reply-verdict.png) | ![Settings: model, email, language, privacy](docs/screenshots/16-settings.png) |
| **Reply verdict** | **Settings** |
| ![Dark mode review](docs/screenshots/18-dark-review.png) | ![Dark mode: My cases](docs/screenshots/19-dark-my-cases.png) |
| **Dark mode** | **Dark mode: My cases** |

## How it works

```mermaid
flowchart LR
    U[You: story + evidence] --> UI[Web app: Next.js]
    UI <--> API[FastAPI]
    API --> G[LangGraph case agent]
    G --> I[intake: OCR + fact extraction]
    I --> C[classify + pick playbook]
    C --> D[draft from template]
    D --> F[fact check: code + model]
    F --> A{You approve?}
    A -- edit / reject --> D
    A -- approve --> S[send: email, or print for post/court]
    S --> W[wait: reminders + deadlines]
    W --> J[judge the reply]
    J -- refused / no reply --> N[next step on the ladder]
    N --> D
    J -- resolved --> R[(case closed)]
    P[(playbooks/: country ladders)] -.-> C
    L[(local LLM via Ollama)] -.-> I & D & F & J
```

- **Playbooks** (`playbooks/<country>/…yaml`) describe each ladder: steps, wait times, deadlines
  and official sources. The resolver picks the most specific one: company → region → country →
  a generic international ladder that works anywhere.
- **Templates** (`templates/<country>/<language>/`) hold the letters. The model only polishes
  tone and language; the structure and every fact come from the template and your case.
- **One process** runs the API and the scheduler (reminders survive restarts). The web app
  (`web/`) only talks to the API, so a future mobile or chat front end can reuse it.
- **Global by design:** every ISO country is listed; money and dates use each case's locale.
  Countries without a local pack get a generic route, labelled as such. v0.1 is English-only
  (app and letters); more languages are coming (see docs/DECISIONS.md).
- **Free by default:** a local model through Ollama; any OpenAI-compatible endpoint works
  (Groq, Gemini, OpenRouter, paid APIs) by changing one line in `.env`.

## Safety

- **Human approval on every message.** Nothing is sent until you click approve. This is
  enforced in code and tested on every send path. The AI has no ability to send.
- **Facts only.** Every amount, date and ID in a draft must come from your case facts; drafts
  that invent anything are sent back. Your own edits are checked too.
- **Polite and firm.** Threats and insults are blocked before approval.
- **Private.** Evidence is encrypted at rest; card numbers, IBANs, national ID numbers and any
  password or one-time code you type are masked in logs, stored text and drafts. Escalate never
  asks for passwords, PINs or OTPs. You get a warning when your AI model runs in the cloud.
- **Not legal advice.** Letters and PDF case files say so. See [SECURITY.md](SECURITY.md).

## Hosted beta (invite-only)

Escalate is self-hosted first. For people who can't run it themselves there is an optional
hosted mode (`DEPLOY_MODE=hosted`), built on free tiers: Vercel (web), Render (API, Frankfurt),
Supabase (Postgres, Google sign-in and encrypted file storage, Frankfurt) and Groq (AI, zero
data retention). In hosted mode:

- people sign in with Google; only invited emails get in (`make invite EMAIL=...`), everyone
  else sees a waitlist;
- every user's cases, letters and evidence are theirs alone (one scoped data layer, 404 for
  anyone else's id, an IDOR test suite over every route);
- the AI provider is fixed by the server, with daily limits per user and overall;
- **Escalate never sends email**: after approving, the user opens the letter in their own email
  app (or copies it, or downloads the PDF) and clicks "I've sent it";
- users can export all their data or delete their account.

Local mode (the default) is unchanged: SQLite, Ollama, no login. Deploy guide:
[docs/DEPLOY_BETA.md](docs/DEPLOY_BETA.md). Threat model: [SECURITY.md](SECURITY.md) ("Hosted beta").

## Supported countries

| Country | Refund refused | Subscription | Scam checklist | Status |
| --- | --- | --- | --- | --- |
| 🌍 Any country | generic ladder | generic ladder | generic | ✅ always available |
| 🇵🇰 Pakistan | seller → marketplace → 15-day legal notice → District Consumer Court | generic | ✅ | needs lawyer review |
| 🇮🇳 India | demand → legal notice → District Consumer Commission | generic | ✅ | starter, needs verification |
| 🇬🇧 United Kingdom | complaint → letter before action → small claim | generic | ✅ | starter, needs verification |
| 🇺🇸 United States | demand → final demand → state attorney general → small claims | generic | ✅ | starter, needs verification |

**Add your country:** see [docs/CONTRIBUTING-PLAYBOOKS.md](docs/CONTRIBUTING-PLAYBOOKS.md). Every
rule must cite an official source.

## Roadmap

- **v0.1** (now): 3 case types, generic + 4 country packs, email/post/court channels, PDF case file.
- **v0.2:** Telegram bot, more UI translations, detect replies in your inbox.
- **v0.3:** more countries from the community, scam packs per bank.
- **v1.0:** multi-user hosting, opt-in anonymous success rates per playbook.

## Contributing

Contributions are welcome, especially country playbooks, UI translations (`web/messages/`) and template reviews by
lawyers or consumer-rights groups. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the
[good first issues](docs/good-first-issues.md). Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

```bash
make test    # offline unit and integration tests (fake LLM, fake email)
make lint    # ruff, mypy and the playbook validator
make web-lint  # eslint and TypeScript for the web app
make web-e2e   # Playwright: smoke, console/hydration guard (light + dark), dark mode, mobile
make evals   # golden-set evals against your model
```

## License

[MIT](LICENSE).

## Acknowledgements

Built with LangGraph, FastAPI, Next.js, Tailwind CSS, shadcn/ui, next-intl, SQLAlchemy, APScheduler, Tesseract, WeasyPrint,
Babel and Ollama. Pakistan's consumer-court route follows the CRCP guide cited in its playbook.
