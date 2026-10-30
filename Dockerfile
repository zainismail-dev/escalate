# Escalate API image. Tesseract (OCR) and Pango (WeasyPrint PDFs) included. Runs as a non-root
# user; uid 1000 matches the usual owner of the ./data bind mount (override: --build-arg UID=).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng tesseract-ocr-urd tesseract-ocr-hin \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
      fonts-dejavu-core fonts-noto-core curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ARG UID=1000
RUN uv sync --frozen --no-dev \
 && mkdir -p /app/data /app/secrets \
 && useradd --uid "$UID" --user-group --no-create-home --home-dir /app --shell /usr/sbin/nologin escalate \
 && chown -R escalate:escalate /app/data /app/secrets
USER escalate

EXPOSE 8000
CMD ["uvicorn", "escalate.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
