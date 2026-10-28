from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_readme_has_every_section() -> None:
    text = (REPO / "README.md").read_text()
    for heading in (
        "## Why it exists",
        "## Quick start",
        "## How it works",
        "## Safety",
        "## Supported countries",
        "## Roadmap",
        "## Contributing",
        "## License",
    ):
        assert heading in text
    assert "```mermaid" in text
    assert "docs/demo.gif" in text
    assert "docs/CONTRIBUTING-PLAYBOOKS.md" in text


def test_linked_local_files_exist() -> None:
    import re

    text = (REPO / "README.md").read_text() + (REPO / "CONTRIBUTING.md").read_text()
    for link in re.findall(r"\]\(((?!https?://|#)[^)]+)\)", text):
        if link.endswith("demo.gif"):
            continue
        assert (REPO / link).exists(), link


def test_issue_templates_are_valid_yaml() -> None:
    names = set()
    for path in (REPO / ".github" / "ISSUE_TEMPLATE").glob("*.yml"):
        data = yaml.safe_load(path.read_text())
        if path.name != "config.yml":
            assert data["name"] and data["body"]
            names.add(data["name"])
    assert names == {"Bug report", "New playbook", "Playbook correction"}


def test_ten_good_first_issues() -> None:
    import re

    text = (REPO / "docs" / "good-first-issues.md").read_text()
    assert len(re.findall(r"^\d+\. \*\*", text, re.M)) == 10
