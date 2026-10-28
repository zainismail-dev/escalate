"""Docker / compose / Makefile sanity (the image itself is built and smoke-tested in CI)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

REPO = Path(__file__).resolve().parents[1]


def test_compose_has_ollama_api_web_ui() -> None:
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    services = compose["services"]
    assert set(services) == {"ollama", "api", "web", "ui"}
    api_env = services["api"]["environment"]
    assert "LLM_BASE_URL=http://ollama:11434/v1" in api_env
    assert all("/app/data" in e for e in api_env if e.startswith(("DATABASE_URL", "EVIDENCE")))
    assert "./data:/app/data" in services["api"]["volumes"]
    ui_env = services["ui"]["environment"]
    assert "API_URL=http://api:8000" in ui_env
    assert "PUBLIC_API_URL=http://localhost:8000" in ui_env
    web = services["web"]
    assert web["ports"] == ["3000:3000"]
    assert web["build"]["args"]["NEXT_PUBLIC_API_URL"] == "http://localhost:8000"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert "WEB_ORIGIN=http://localhost:3000" in api_env  # CORS allows the web app only


def test_dockerfile_matches_spec() -> None:
    text = (REPO / "Dockerfile").read_text()
    assert text.startswith("#") and "FROM python:3.12-slim" in text
    for pkg in ("tesseract-ocr", "tesseract-ocr-urd", "libpango-1.0-0"):
        assert pkg in text
    assert "uv sync --frozen" in text


def test_makefile_targets() -> None:
    text = (REPO / "Makefile").read_text()
    for target in ("setup:", "up:", "test:", "evals:", "demo-data:", "web-dev:", "web-e2e:"):
        assert f"\n{target}" in text


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
def test_setup_env_script(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "setup_env.sh", tmp_path / "scripts")
    shutil.copy(REPO / ".env.example", tmp_path)
    run = ["sh", "scripts/setup_env.sh", "some-model:7b"]
    subprocess.run(run, cwd=tmp_path, check=True, capture_output=True)
    env = dict(
        line.split("=", 1)
        for line in (tmp_path / ".env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    key = env["FERNET_KEY"].strip()
    Fernet(key.encode())  # a valid key
    assert env["MODEL_SMART"].strip() == "some-model:7b"
    subprocess.run(run, cwd=tmp_path, check=True, capture_output=True)
    again = (tmp_path / ".env").read_text()
    assert f"FERNET_KEY={key}" in again  # never replaced once set
