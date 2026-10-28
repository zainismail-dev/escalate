# Escalate: one-command install. `make setup && make up`, then open http://localhost:3000
MODEL ?= llama3.1:8b

.PHONY: setup up down logs test lint evals pull api demo-data web-install web-dev web-lint web-build web-e2e screenshots

setup:            ## create .env (FERNET_KEY, model), build images, pull the model
	./scripts/setup_env.sh "$(MODEL)"
	docker compose build
	docker compose up -d ollama
	docker compose exec ollama ollama pull "$(MODEL)"

pull:             ## pull (another) model: make pull MODEL=name
	docker compose exec ollama ollama pull "$(MODEL)"

up:               ## start everything
	docker compose up -d
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
	curl -fsS -X POST $(API_URL)/demo/seed && echo

web-install:
	cd web && npm ci

web-dev:          ## the web app with hot reload on http://localhost:3000 (API on :8000)
	cd web && NEXT_PUBLIC_API_URL=$(API_URL) npm run dev

web-lint:         ## eslint + TypeScript for the web app
	cd web && npm run lint && npm run typecheck

web-build:
	cd web && NEXT_PUBLIC_API_URL=$(API_URL) npm run build

web-e2e:          ## Playwright smoke tests (smoke, rtl, dark, mobile) against WEB_URL + API_URL
	cd web && WEB_URL=$(WEB_URL) API_URL=$(API_URL) npx playwright test --project=smoke --project=rtl --project=dark --project=mobile

screenshots:      ## docs/screenshots/*.png; wipes and re-seeds the API (use a throwaway, DEMO_MODE=true)
	cd web && E2E_RESET=1 WEB_URL=$(WEB_URL) API_URL=$(API_URL) npx playwright test --project=screenshots
