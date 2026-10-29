# Escalate: one-command install. `make setup && make up`, then open http://localhost:3000
MODEL ?= llama3.1:8b

.PHONY: setup up down logs test lint evals pull api demo-data web-install web-dev web-lint web-build web-e2e screenshots \
	demo-fixtures demo-build demo-e2e hooks security zap

setup:            ## create .env (FERNET_KEY, model), build images, pull the model
	./scripts/setup_env.sh "$(MODEL)"
	docker compose build
	docker compose up -d ollama
	docker compose exec ollama ollama pull "$(MODEL)"

pull:             ## pull (another) model: make pull MODEL=name
	docker compose exec ollama ollama pull "$(MODEL)"

ALLOW_LAN ?= false

up:               ## start everything (localhost only; `make up ALLOW_LAN=true` to open it to your network)
ifeq ($(ALLOW_LAN),true)
	@echo "################################################################################"
	@echo "#  WARNING: ALLOW_LAN=true. Escalate has NO LOGIN. Anyone on your network can   #"
	@echo "#  read your cases and evidence, change settings and SEND LETTERS as you.        #"
	@echo "#  Also set ALLOWED_HOSTS and WEB_ORIGIN to this machine's LAN address.          #"
	@echo "################################################################################"
	BIND_ADDR=0.0.0.0 ALLOW_LAN=true docker compose up -d
else
	docker compose up -d
endif
	@echo "Web app:      http://localhost:3000"
	@echo "API:          http://localhost:8000/docs"
	@echo "Streamlit UI: http://localhost:8501 (dev)"

down:
	docker compose down

logs:
	docker compose logs -f api web ui

test:             ## unit tests (offline: fake LLM, fake SMTP)
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy escalate
	uv run python -m escalate.playbooks.validate playbooks/

evals:            ## golden-set evals against the model in .env; writes evals/report.md
	uv run python -m evals.run --suite all

API_URL ?= http://localhost:8000
WEB_URL ?= http://localhost:3000

api:              ## the API with auto-reload on http://localhost:8000 (watches escalate/ only)
	uv run uvicorn escalate.api.main:app --reload --reload-dir escalate

demo-data:        ## seed 4 fictional demo cases (PK, IN, GB, US) into the running API
	curl -fsS -X POST -H "Origin: $(WEB_URL)" -H "X-Escalate-Request: 1" $(API_URL)/demo/seed && echo

web-install:
	cd web && npm ci

web-dev:          ## the web app with hot reload on http://localhost:3000 (API on :8000)
	cd web && NEXT_PUBLIC_API_URL=$(API_URL) npm run dev

web-lint:         ## eslint + TypeScript for the web app
	cd web && npm run lint && npm run typecheck

web-build:
	cd web && NEXT_PUBLIC_API_URL=$(API_URL) npm run build

web-e2e:          ## Playwright: smoke, console guard (light+dark), rtl, dark, mobile against WEB_URL + API_URL
	cd web && WEB_URL=$(WEB_URL) API_URL=$(API_URL) npx playwright test --project=smoke --project=guard --project=rtl --project=dark --project=mobile

screenshots:      ## docs/screenshots/*.png; wipes and re-seeds the API (use a throwaway, DEMO_MODE=true)
	cd web && E2E_RESET=1 WEB_URL=$(WEB_URL) API_URL=$(API_URL) npx playwright test --project=screenshots

demo-fixtures:    ## rebuild the live demo's sample data (web/src/demo/*.json) from a throwaway API
	uv run python scripts/demo_fixtures.py

demo-build:       ## the static live demo (no API): what Vercel builds; then scans the bundle
	cd web && npm run build:demo && node scripts/scan-bundle.mjs --demo

demo-e2e:         ## Playwright against a running demo build (WEB_URL); no API needed
	cd web && DEMO_E2E=1 WEB_URL=$(WEB_URL) npx playwright test --project=demo --project=guard

hooks:            ## install the pre-commit hooks (gitleaks, no .env/*.db, ruff)
	uvx pre-commit install

security:         ## the CI security checks, locally (needs gitleaks on PATH)
	gitleaks git . --redact
	# The Intel-macOS-only cryptography pin is a documented residual (docs/SECURITY_AUDIT.md).
	uv export --frozen --no-hashes --no-emit-project --all-groups \
	  | grep -v "platform_machine == 'x86_64' and sys_platform == 'darwin'" > /tmp/escalate-reqs.txt
	uvx pip-audit -r /tmp/escalate-reqs.txt --disable-pip --no-deps --strict
	uvx bandit -c pyproject.toml -r escalate ui -q
	uvx semgrep scan --config p/python --config p/fastapi --config p/secrets --config p/typescript --config p/react --config p/nextjs --metrics=off --error -q
	cd web && npm audit --audit-level=high
	uv run pytest -q tests/security

ZAP ?= zap.sh
zap:              ## OWASP ZAP baseline against WEB_URL + API_URL (throwaway DEMO_MODE instances!)
	mkdir -p zap-out && WEB_URL=$(WEB_URL) API_URL=$(API_URL) ZAP_OUT=$(CURDIR)/zap-out $(ZAP) -cmd -autorun $(CURDIR)/.zap/baseline.yaml
	uv run python .zap/gate.py zap-out/zap-report.json
