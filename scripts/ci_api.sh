#!/usr/bin/env bash
# CI only: the API in DEMO_MODE on throwaway data in /tmp/esc, with no AI model.
set -euo pipefail
export FERNET_KEY=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
mkdir -p /tmp/esc
DEMO_MODE=true DATABASE_URL=sqlite:////tmp/esc/escalate.db CHECKPOINT_DB=/tmp/esc/cp.db \
EVIDENCE_DIR=/tmp/esc/ev ESCALATE_SETTINGS_FILE=/tmp/esc/settings.json \
MODEL_SMART=none MODEL_FAST=none LLM_BASE_URL=http://127.0.0.1:9/v1 \
WEB_ORIGIN=http://localhost:3000,http://localhost:3001 \
nohup uv run uvicorn escalate.api.main:app --port 8000 > /tmp/esc/api.log 2>&1 &
for i in $(seq 30); do curl -fsS "${API_URL:-http://localhost:8000}/health" && exit 0; sleep 1; done
echo "API did not start" && tail -50 /tmp/esc/api.log && exit 1
