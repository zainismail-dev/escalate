import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from escalate.playbooks import loader
from escalate.playbooks.models import Step
from escalate.playbooks.resolver import resolve
from escalate.playbooks.validate import main as validate_main
from escalate.playbooks.validate import validate

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    loader.clear_cache()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of the real playbooks + templates that tests can break."""
    shutil.copytree(REPO / "playbooks", tmp_path / "playbooks")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    return tmp_path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _edit(path: Path, **changes: object) -> None:
    data = yaml.safe_load(path.read_text())
    data.update(changes)
    _write(path, data)


def _pk(tree: Path) -> Path:
    return tree / "playbooks/pk/ecommerce/refund_refused.yaml"


# --- the real repo -------------------------------------------------------------


def test_repo_playbooks_validate() -> None:
    assert validate_main([str(REPO / "playbooks")]) == 0


def test_every_repo_playbook_loads() -> None:
    books = loader.load_all(REPO / "playbooks")
    assert {"intl-generic-refund-refused", "pk-ecommerce-refund-refused"} <= set(books)


# --- resolver ------------------------------------------------------------------


def test_resolver_country_with_region(tree: Path) -> None:
    pb = resolve("PK", "PK-SD", "refund_refused", root=tree / "playbooks")
    assert pb.id == "pk-ecommerce-refund-refused"


def test_resolver_country_without_known_region(tree: Path) -> None:
    pb = resolve("pk", None, "refund_refused", root=tree / "playbooks")
    assert pb.id == "pk-ecommerce-refund-refused"


def test_resolver_region_not_covered_falls_back_to_generic(tree: Path) -> None:
    pb = resolve("PK", "PK-GB", "refund_refused", root=tree / "playbooks")
    assert pb.id == "intl-generic-refund-refused"


def test_resolver_unknown_country_falls_back_to_generic(tree: Path) -> None:
    for cc in ("BR", None):
        pb = resolve(cc, None, "refund_refused", root=tree / "playbooks")
        assert pb.id == "intl-generic-refund-refused"
        assert pb.generic


def test_resolver_full_fallback_chain(tree: Path) -> None:
    base = yaml.safe_load(_pk(tree).read_text())
    country_wide = {**base, "id": "pk-country", "regions": []}
    _write(tree / "playbooks/pk/general/refund_refused.yaml", country_wide)
    company = {**base, "id": "pk-acme", "regions": [], "company": "acme_electronics"}
    _write(tree / "playbooks/pk/ecommerce/refund_refused.acme.yaml", company)
    root = tree / "playbooks"

    assert resolve("PK", "PK-SD", "refund_refused", "ACME Electronics", root=root).id == "pk-acme"
    assert resolve("PK", "PK-SD", "refund_refused", "Other Co", root=root).id == (
        "pk-ecommerce-refund-refused"
    )
    assert resolve("PK", "PK-GB", "refund_refused", root=root).id == "pk-country"
    assert resolve("IN", None, "refund_refused", "ACME Electronics", root=root).id == (
        "intl-generic-refund-refused"
    )


def test_resolver_picks_case_type(tree: Path) -> None:
    assert resolve("PK", None, "scam", root=tree / "playbooks").id == "intl-generic-scam"


def test_step_when() -> None:
    step = Step(id="s", channel="email", template="x/y.md.j2", when="platform_name is set")
    assert step.applies({"platform_name": "Daraz"})
    assert not step.applies({})
    assert not step.applies({"platform_name": "  "})
    neg = Step(id="s", channel="email", template="x/y.md.j2", when="platform_name is not set")
    assert neg.applies({})


# --- validator failures --------------------------------------------------------


def _errors(tree: Path, today: date | None = None) -> list[str]:
    return validate(tree / "playbooks", tree / "templates", today=today).errors


def test_clean_tree_has_no_errors(tree: Path) -> None:
    assert _errors(tree) == []


def test_schema_error_fails(tree: Path) -> None:
    _edit(_pk(tree), country="Pakistan")
    errs = _errors(tree)
    assert any("schema: country" in e for e in errs)


def test_non_iso_region_fails(tree: Path) -> None:
    _edit(_pk(tree), regions=["sindh"])
    assert any("schema: regions" in e for e in _errors(tree))


def test_missing_template_fails(tree: Path) -> None:
    (tree / "templates/pk/en/legal_notice_15_day.md.j2").unlink()
    assert any("missing template pk/legal_notice_15_day.md.j2" in e for e in _errors(tree))


def test_missing_adds_if_late_template_fails(tree: Path) -> None:
    (tree / "templates/pk/en/condonation_of_delay.md.j2").unlink()
    assert any("condonation_of_delay" in e for e in _errors(tree))


def test_unknown_step_target_fails(tree: Path) -> None:
    data = yaml.safe_load(_pk(tree).read_text())
    data["steps"][0]["on_no_reply"] = "s9_nowhere"
    _write(_pk(tree), data)
    assert any("unknown step 's9_nowhere'" in e for e in _errors(tree))


def test_missing_sources_fails(tree: Path) -> None:
    _edit(_pk(tree), sources=[])
    assert any("sources" in e for e in _errors(tree))
    data = yaml.safe_load(_pk(tree).read_text())
    del data["sources"]
    _write(_pk(tree), data)
    assert any("'sources' is a required property" in e for e in _errors(tree))


def test_template_using_non_fact_fails(tree: Path) -> None:
    tpl = tree / "templates/pk/en/seller_written_demand.md.j2"
    tpl.write_text(tpl.read_text() + "\nYou owe me {{ invented_penalty }}.\n")
    assert any("invented_penalty" in e for e in _errors(tree))


def test_template_syntax_error_fails(tree: Path) -> None:
    (tree / "templates/pk/en/seller_written_demand.md.j2").write_text("{% if %}")
    assert any("syntax error" in e for e in _errors(tree))


def test_duplicate_id_fails(tree: Path) -> None:
    shutil.copy(_pk(tree), tree / "playbooks/pk/ecommerce/refund_refused.copy.yaml")
    assert any("duplicate id" in e for e in _errors(tree))


def test_undeclared_when_fact_fails(tree: Path) -> None:
    data = yaml.safe_load(_pk(tree).read_text())
    data["steps"][1]["when"] = "marketplace is set"
    _write(_pk(tree), data)
    assert any("undeclared fact 'marketplace'" in e for e in _errors(tree))


def test_stale_last_verified_only_warns(tree: Path) -> None:
    report = validate(tree / "playbooks", tree / "templates", today=date(2028, 1, 1))
    assert report.errors == []
    assert any("more than 12 months old" in w for w in report.warnings)


def test_cli_exit_code(tree: Path) -> None:
    _edit(_pk(tree), version="one")
    assert validate_main([str(tree / "playbooks")]) == 1
