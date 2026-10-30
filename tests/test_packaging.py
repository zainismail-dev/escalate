"""Docker / compose / Makefile sanity (the image itself is built and smoke-tested in CI)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

REPO = Path(__file__).resolve().parents[1]


def test_compose_has_ollama_api_web() -> None:
    """The Streamlit UI is retired from compose (second review N1); see tests/security."""
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    services = compose["services"]
    assert set(services) == {"ollama", "api", "web"}
    api_env = services["api"]["environment"]
    assert "LLM_BASE_URL=http://ollama:11434/v1" in api_env
    assert all("/app/data" in e for e in api_env if e.startswith(("DATABASE_URL", "EVIDENCE")))
    assert "./data:/app/data" in services["api"]["volumes"]
    web = services["web"]
    assert web["ports"] == ["${BIND_ADDR:-127.0.0.1}:3000:3000"]
    assert web["build"]["args"]["NEXT_PUBLIC_API_URL"] == "http://localhost:8000"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert "WEB_ORIGIN=${WEB_ORIGIN:-http://localhost:3000}" in api_env  # CORS: the web app only
    assert "ALLOWED_HOSTS=${ALLOWED_HOSTS:-localhost,127.0.0.1}" in api_env


def test_compose_publishes_ports_on_localhost_only() -> None:
    """Review #4: every port was published on all interfaces, so anyone on the LAN had full
    unauthenticated access. LAN exposure is now opt-in (make up ALLOW_LAN=true)."""
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    for name, svc in compose["services"].items():
        for port in svc.get("ports", []):
            assert port.startswith("${BIND_ADDR:-127.0.0.1}:"), (name, port)
    make = (REPO / "Makefile").read_text()
    assert "ifeq ($(ALLOW_LAN),true)" in make and "NO LOGIN" in make
    assert "BIND_ADDR=0.0.0.0 ALLOW_LAN=true docker compose up -d" in make


def test_dockerfile_matches_spec() -> None:
    text = (REPO / "Dockerfile").read_text()
    assert text.startswith("#") and "FROM python:3.12-slim" in text
    for pkg in ("tesseract-ocr", "tesseract-ocr-urd", "libpango-1.0-0"):
        assert pkg in text
    assert "uv sync --frozen" in text


def test_makefile_targets() -> None:
    text = (REPO / "Makefile").read_text()
    for target in (
        "setup:",
        "up:",
        "test:",
        "evals:",
        "api:",
        "demo-data:",
        "web-dev:",
        "web-e2e:",
    ):
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


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
def test_setup_env_keeps_real_key_and_drops_blank_duplicates(tmp_path: Path) -> None:
    """A blank FERNET_KEY= after the real one (template leftover) used to make the script
    generate a new key and overwrite the real one, losing access to encrypted evidence."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "setup_env.sh", tmp_path / "scripts")
    real = Fernet.generate_key().decode()
    (tmp_path / ".env").write_text(
        f"FERNET_KEY={real}\nMODEL_SMART=m\nFERNET_KEY=                # template comment\n"
    )
    subprocess.run(["sh", "scripts/setup_env.sh"], cwd=tmp_path, check=True, capture_output=True)
    lines = [ln for ln in (tmp_path / ".env").read_text().splitlines() if ln.startswith("FERNET")]
    assert lines == [f"FERNET_KEY={real}"]


def test_ollama_is_not_published_and_is_pinned() -> None:
    """Third review L1: Ollama (no auth) was published on the host, and on the LAN with
    ALLOW_LAN=true; the image was unpinned."""
    ollama = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]["ollama"]
    assert "ports" not in ollama
    image, _, tag = ollama["image"].partition(":")
    assert image == "ollama/ollama"
    assert tag and tag != "latest" and tag[0].isdigit()
