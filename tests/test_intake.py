from sqlalchemy.orm import Session

from escalate.agent.intake import extract, save_answers
from escalate.db.models import Case, Evidence
from tests.fakes.fake_llm import FakeLLM

REQUIRED = ["buyer_name", "seller_name", "order_id", "amount", "currency", "remedy_wanted"]


def _case(db: Session) -> tuple[Case, Evidence]:
    case = Case(description="LED broke")
    db.add(case)
    db.flush()
    ev = Evidence(case_id=case.id, kind="image", file_path="x", sha256="0" * 64)
    db.add(ev)
    db.flush()
    return case, ev


def test_extract_saves_confident_facts_with_sources(db: Session) -> None:
    case, ev = _case(db)
    llm = FakeLLM(
        script=[
            {
                "facts": {
                    "buyer_name": {"value": "Ali Khan", "evidence_id": None, "confidence": 0.95},
                    "order_id": {"value": "BM-48213", "evidence_id": ev.id, "confidence": 0.9},
                    "amount": {"value": 45000, "evidence_id": ev.id, "confidence": 0.9},
                    "currency": {"value": "PKR", "evidence_id": ev.id, "confidence": 0.9},
                    "seller_name": {"value": "Maybe BrightMart", "confidence": 0.3},
                    "remedy_wanted": {"value": None, "confidence": 0.1},
                    "favourite_colour": {"value": "blue", "confidence": 1.0},
                },
                "missing": ["remedy_wanted"],
            }
        ]
    )
    result = extract(
        db, case, "My LED broke", [(ev.id, "Order BM-48213 45000 PKR")], REQUIRED, llm=llm
    )

    assert result.facts == {
        "buyer_name": "Ali Khan",
        "order_id": "BM-48213",
        "amount": "45000",
        "currency": "PKR",
    }
    # a guess (confidence < 0.5) is never stored; it goes to missing
    assert result.missing == ["seller_name", "remedy_wanted"]
    by_key = {f.key: f for f in case.facts}
    assert by_key["order_id"].source_evidence_id == ev.id
    assert by_key["buyer_name"].source_evidence_id is None
    assert "favourite_colour" not in by_key
    assert case.events[-1].type == "facts_extracted"
    prompt = llm.calls[0][0]
    assert "Required keys: buyer_name, seller_name" in prompt
    assert f"[evidence_id={ev.id}]" in prompt
    assert llm.calls[0][1] == "smart"


def test_unknown_evidence_id_is_dropped(db: Session) -> None:
    case, _ = _case(db)
    llm = FakeLLM(script=[{"facts": {"order_id": {"value": "X1", "evidence_id": 999}}}])
    extract(db, case, "order X1", [], ["order_id"], llm=llm)
    assert case.facts[0].source_evidence_id is None


def test_user_answers_are_not_overwritten_by_lower_confidence(db: Session) -> None:
    case, _ = _case(db)
    save_answers(db, case, {"order_id": "REAL-1", "seller_name": ""})
    llm = FakeLLM(script=[{"facts": {"order_id": {"value": "WRONG", "confidence": 0.8}}}])
    result = extract(db, case, "x", [], ["order_id", "seller_name"], llm=llm)
    assert result.facts["order_id"] == "REAL-1"
    assert result.missing == ["seller_name"]


def test_bad_json_is_retried(db: Session) -> None:
    case, _ = _case(db)
    llm = FakeLLM(script=["I think the order is X1", {"facts": {"order_id": {"value": "X1"}}}])
    result = extract(db, case, "order X1", [], ["order_id"], llm=llm)
    assert result.missing == []
    assert len(llm.calls) == 2
