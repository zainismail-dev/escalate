import json

import httpx
import openai
import pytest
from pydantic import BaseModel

from escalate.config import Settings
from escalate.llm.client import LLMClient
from escalate.llm.privacy import is_cloud
from escalate.llm.structured import StructuredOutputError, ask_json, extract_json
from tests.fakes.fake_llm import FakeLLM


class Answer(BaseModel):
    name: str
    amount: float


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {"model_smart": "smart-m", "model_fast": "fast-m"}
    base.update(kw)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


# --- structured output -------------------------------------------------------


def test_extract_json_from_fenced_reply_with_trailing_comma() -> None:
    text = 'Sure!\n```json\n{"name": "a", "amount": 3,}\n```\nanything else?'
    assert extract_json(text) == {"name": "a", "amount": 3}


def test_extract_json_from_surrounding_prose() -> None:
    assert extract_json('Here: {"a": {"b": 1}} done') == {"a": {"b": 1}}


def test_ask_json_retries_with_validation_error() -> None:
    llm = FakeLLM(script=[{"name": "x"}, {"name": "x", "amount": 5}])
    result = ask_json(llm, "PROMPT", Answer, slot="fast")
    assert result == Answer(name="x", amount=5)
    assert len(llm.calls) == 2
    assert all(slot == "fast" for _, slot in llm.calls)
    assert "amount" in llm.calls[1][0]  # the validation error is appended
    assert llm.calls[1][0].startswith("PROMPT")
    assert "ONLY one valid JSON object" in llm.calls[1][0]  # and the instruction is stricter


def test_ask_json_retries_once_then_gives_up() -> None:
    llm = FakeLLM(script=["nope", "nope", {"name": "late", "amount": 1}])
    with pytest.raises(StructuredOutputError) as err:
        ask_json(llm, "P", Answer)
    assert len(llm.calls) == 2
    assert err.value.category == "invalid_json"


# --- client and 429 backoff --------------------------------------------------


def _mock_openai(responses: list[httpx.Response]) -> tuple[openai.OpenAI, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)

    client = openai.OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="x",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return client, seen


def _ok(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
        },
    )


def _rate_limited() -> httpx.Response:
    return httpx.Response(429, json={"error": {"message": "slow down"}})


def test_complete_backs_off_exponentially_on_429() -> None:
    client, seen = _mock_openai([_rate_limited(), _rate_limited(), _ok("hello")])
    sleeps: list[float] = []
    llm = LLMClient(_settings(), client=client, base_delay=1.0, sleep=sleeps.append)
    assert llm.complete("hi", slot="fast") == "hello"
    assert sleeps == [1.0, 2.0]
    assert json.loads(seen[-1].content)["model"] == "fast-m"


def test_complete_raises_after_max_rate_retries() -> None:
    client, _ = _mock_openai([_rate_limited() for _ in range(3)])
    llm = LLMClient(_settings(), client=client, max_rate_retries=2, sleep=lambda _: None)
    with pytest.raises(openai.RateLimitError):
        llm.complete("hi")


def test_fast_slot_falls_back_to_smart_model() -> None:
    llm = LLMClient(_settings(model_fast=""), client=_mock_openai([])[0])
    assert llm.model_for("fast") == "smart-m"


def test_missing_model_is_a_clear_error() -> None:
    llm = LLMClient(_settings(model_smart="<local-instruct-model>"), client=_mock_openai([])[0])
    with pytest.raises(RuntimeError, match="MODEL_SMART"):
        llm.model_for("smart")


# --- privacy -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "warn", "expected"),
    [
        ("http://localhost:11434/v1", True, False),
        ("http://127.0.0.1:11434/v1", True, False),
        ("http://ollama:11434/v1", True, False),
        ("https://api.groq.com/openai/v1", True, True),
        ("https://openrouter.ai/api/v1", False, False),
    ],
)
def test_is_cloud(url: str, warn: bool, expected: bool) -> None:
    assert is_cloud(_settings(llm_base_url=url, cloud_privacy_warning=warn)) is expected


def test_one_ai_call_has_a_short_request_timeout_and_a_total_time_budget() -> None:
    """M3: a slow or rate-limiting provider can't hold an agent run for many minutes."""
    client, seen = _mock_openai([_rate_limited() for _ in range(6)])
    now = [0.0]
    sleeps: list[float] = []

    def sleep(d: float) -> None:
        sleeps.append(d)
        now[0] += d

    settings = _settings(llm_timeout_s=60, llm_total_timeout_s=10)
    llm = LLMClient(settings, client=client, base_delay=4.0, sleep=sleep, clock=lambda: now[0])
    with pytest.raises(openai.RateLimitError):
        llm.complete("hi")
    assert sum(sleeps) < 10 and len(seen) == 2  # waited 4 s, then 8 s would pass the budget
    real = LLMClient(_settings(llm_base_url="https://api.groq.test/openai/v1"))
    assert real._client.timeout == 60


def test_each_request_gets_at_most_the_time_left(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _mock_openai([_ok("hello")])
    llm = LLMClient(_settings(llm_timeout_s=60, llm_total_timeout_s=90), client=client)
    seen: list[float] = []
    real_create = llm._create

    def spy(model: str, prompt: str, extras: dict[str, object], timeout: float) -> str:
        seen.append(timeout)
        return real_create(model, prompt, extras, timeout)

    monkeypatch.setattr(llm, "_create", spy)
    assert llm.complete("hi") == "hello"
    assert seen == [60]
