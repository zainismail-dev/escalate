# Escalate: one-command install. `make setup && make up`, then open http://localhost:8501
MODEL ?= llama3.1:8b

.PHONY: setup up down logs test lint evals pull

setup:            ## create .env (FERNET_KEY, model), build images, pull the model
	./scripts/setup_env.sh "$(MODEL)"
	docker compose build
	docker compose up -d ollama
	docker compose exec ollama ollama pull "$(MODEL)"

pull:             ## pull (another) model: make pull MODEL=name
	docker compose exec ollama ollama pull "$(MODEL)"

up:               ## start everything
	docker compose up -d
	@echo "UI:  http://localhost:8501"
	@echo "API: http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f api ui

test:             ## unit tests (offline: fake LLM, fake SMTP)
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy escalate
	uv run python -m escalate.playbooks.validate playbooks/

evals:            ## golden-set evals against the model in .env; writes evals/report.md
	uv run python -m evals.run --suite all
