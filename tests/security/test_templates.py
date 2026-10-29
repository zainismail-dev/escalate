"""Server-side template injection: case facts are data, never template source."""

from pathlib import Path

import pytest
from jinja2.exceptions import SecurityError

from escalate.export.case_pdf import _env as case_env
from escalate.templates_engine import make_env, render_file

PAYLOADS = [
    "{{7*7}}",
    "{{ config }}",
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{% for x in range(3) %}x{% endfor %}",
    "{{ self.__init__.__globals__ }}",
    "${7*7} #{7*7} <%= 7*7 %>",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_fact_values_render_literally(tmp_path: Path, payload: str) -> None:
    tpl = tmp_path / "letter.md.j2"
    tpl.write_text("Dear {{ seller_name }},\nOrder {{ order_id }}.\n", encoding="utf-8")
    out = render_file(tpl, {"seller_name": payload, "order_id": "BM-1"})
    assert out == f"Dear {payload},\nOrder BM-1.\n"
    assert "49" not in out.replace(payload, "")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_letters_with_injected_facts_render_literally(payload: str) -> None:
    """The real PK template, with every fact replaced by an injection payload."""
    from escalate.playbooks.loader import load_file
    from escalate.templates_engine import render_step
    from tests.factories import LED_FACTS

    pb = load_file(next(Path("playbooks/pk").rglob("refund_refused.yaml")))
    facts = {k: payload for k in LED_FACTS} | {"amount": "45000", "currency": "PKR"}
    out = render_step(pb, pb.steps[0], facts, "en", country="PK")
    assert payload in out.body
    rest = out.body.replace(payload, "")
    assert "<class" not in rest and "__globals__" not in rest and "49" not in rest


def test_the_sandbox_blocks_attribute_escapes_in_templates() -> None:
    """Defence in depth should a contributed template try it."""
    env = make_env()
    with pytest.raises(SecurityError):
        env.from_string("{{ ''.__class__.__mro__[1].__subclasses__() }}").render()
    with pytest.raises(SecurityError):
        case_env.from_string("{{ x.__init__.__globals__ }}").render(x=object())


def test_case_file_html_is_autoescaped() -> None:
    out = case_env.from_string("<p>{{ v }}</p>").render(v="<script>alert(1)</script>")
    assert out == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
