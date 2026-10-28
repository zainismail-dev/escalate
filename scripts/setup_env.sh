#!/bin/sh
# Create .env from .env.example, generate FERNET_KEY and set the model names (portable sh).
set -e
MODEL="${1:-llama3.1:8b}"
[ -f .env ] || cp .env.example .env
tmp=$(mktemp)
key=""
if grep -q '^FERNET_KEY= *\(#.*\)\{0,1\}$' .env; then
  # A Fernet key is 32 random bytes, url-safe base64 encoded.
  key=$(openssl rand -base64 32 | tr '+/' '-_')
fi
awk -v key="$key" -v model="$MODEL" '
  /^FERNET_KEY=/ && key != "" { print "FERNET_KEY=" key; next }
  /^MODEL_SMART=<|^MODEL_SMART= *$/ { print "MODEL_SMART=" model; next }
  /^MODEL_FAST=<|^MODEL_FAST= *$/ { print "MODEL_FAST=" model; next }
  { print }
' .env > "$tmp" && mv "$tmp" .env
mkdir -p data secrets
echo ".env ready (model: $(grep '^MODEL_SMART=' .env | cut -d= -f2 | cut -d' ' -f1))"
