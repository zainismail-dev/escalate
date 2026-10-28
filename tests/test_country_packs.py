import re
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from escalate.agent.checklist import load_checklist
from escalate.agent.fact_check import code_check
from escalate.playbooks import loader
from escalate.playbooks.resolver import resolve
from escalate.playbooks.validate import validate
from escalate.templates_engine import render_step
from tests.factories import LED_FACTS

REPO = Path(__file__).resolve().parents[1]
FULL = {
    **LED_FACTS,
    "buyer_address": "1 Main St",
    "seller_address": "2 Shop Rd",
    "authority_name": "Consumer Office",
}


@pytest.fixture(autouse=True)
def _fresh() -> None:
    loader.clear_cache()


@pytest.mark.parametrize(
    ("country", "playbook"),
    [
        ("IN", "in-general-refund-refused"),
        ("GB", "gb-general-refund-refused"),
        ("US", "us-general-refund-refused"),
        ("PK", "pk-ecommerce-refund-refused"),
        ("FR", "intl-generic-refund-refused"),
    ],
)
def test_resolver_picks_country_pack(country: str, playbook: str) -> None:
    assert resolve(country, None, "refund_refused").id == playbook


@pytest.mark.parametrize(
    "pid", ["in-general-refund-refused", "gb-general-refund-refused", "us-general-refund-refused"]
)
def test_every_step_renders_facts_only(pid: str) -> None:
    pb = loader.get_playbook(pid)
    for step in pb.steps:
        r = render_step(pb, step, FULL, "en", today=date(2026, 10, 28), country=pb.country)
        text = f"{r.subject}\n{r.body}"
        assert "BM-48213" in text and "None" not in text
        assert code_check(text, FULL, text) == []


def test_no_invented_urls_or_phone_numbers_in_country_packs() -> None:
    url = re.compile(r"https?://")
    phone = re.compile(r"\+?\d[\d\s-]{6,}\d")
    for cc in ("in", "gb", "us"):
        for p in (REPO / "playbooks" / cc).rglob("*.yaml"):
            text = p.read_text()
            assert not url.search(text), p
            assert not phone.search(text.replace("2026-10-28", "")), p
            assert "TODO" in text, f"{p} must list what to verify"
        for p in (REPO / "templates" / cc).rglob("*.j2"):
            assert not url.search(p.read_text()), p
            assert not re.search(r"\b[Ss]ection \d", p.read_text()), p


@pytest.mark.parametrize("cc", ["PK", "IN", "GB", "US"])
def test_country_scam_checklists(cc: str) -> None:
    cl = load_checklist(cc)
    assert cl.country == cc
    assert cl.items[0].id == "call_bank"
    assert any("OTP" in w for w in cl.warnings)


def test_checklist_without_safety_warning_fails(tmp_path: Path) -> None:
    shutil.copytree(REPO / "playbooks", tmp_path / "playbooks")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    path = tmp_path / "playbooks/gb/scam_checklist.yaml"
    data = yaml.safe_load(path.read_text())
    data["warnings"] = ["be careful"]
    path.write_text(yaml.safe_dump(data))
    errors = validate(tmp_path / "playbooks", tmp_path / "templates").errors
    assert any("recovery scammers" in e for e in errors)
