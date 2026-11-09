"""gpt-oss on Groq's OpenAI-compatible API. Responses follow Groq's documented shape: the answer
in `message.content`, the model's thinking in `message.reasoning`."""

import json
import logging
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel

from escalate.config import Settings
from escalate.llm.client import LLMBadOutput, LLMClient, LLMMisconfigured
from escalate.llm.structured import StructuredOutputError, ask_json, extract_json

GPT_OSS = {"model_smart": "openai/gpt-oss-120b", "model_fast": "openai/gpt-oss-20b"}
SECRET_PROMPT = "PROMPT-WITH-CASE-TEXT"


class Letter(BaseModel):
    subject: str
    body: str


DECOY = '{"subject": "decoy", "body": "decoy"}'


def completion(content: str | None, reasoning: str = DECOY) -> Any:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1790000000,
            "model": "openai/gpt-oss-120b",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content, "reasoning": reasoning},
                }
            ],
            "usage": {"prompt_tokens": 90, "completion_tokens": 210, "total_tokens": 300},
        },
    )


def groq_error(status: int, code: str, message: str = "see docs") -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"message": message, "type": "invalid_request_error", "code": code}}
    )


def client_for(
    responses: list[httpx.Response], **settings: Any
) -> tuple[LLMClient, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return responses.pop(0)

    raw = openai.OpenAI(
        base_url="https://api.groq.test/openai/v1",
        api_key="x",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    s = Settings(_env_file=None, **{**GPT_OSS, **settings})  # type: ignore[arg-type]
    return LLMClient(s, client=raw, sleep=lambda _: None), seen


def test_only_message_content_is_used_never_the_reasoning_field() -> None:
    llm, _ = client_for([completion("the answer", reasoning="my private thoughts")])
    assert llm.complete("hi") == "the answer"


def test_reasoning_only_reply_is_bad_output_not_the_reasoning_text() -> None:
    for empty in (None, "", "  \n"):
        llm, _ = client_for([completion(empty, reasoning="I should write a letter")])
        with pytest.raises(LLMBadOutput):
            llm.complete("hi")


def test_gpt_oss_gets_low_reasoning_effort_and_json_mode() -> None:
    llm, seen = client_for([completion("{}")])
    llm.complete("reply in JSON", slot="fast", json_mode=True)
    assert seen[0]["model"] == "openai/gpt-oss-20b"
    assert seen[0]["reasoning_effort"] == "low"
    assert seen[0]["response_format"] == {"type": "json_object"}


def test_plain_text_calls_have_no_json_mode() -> None:
    llm, seen = client_for([completion("pong")])
    llm.complete("ping")
    assert "response_format" not in seen[0] and seen[0]["reasoning_effort"] == "low"


def test_reasoning_effort_can_be_turned_off() -> None:
    llm, seen = client_for([completion("pong")], llm_reasoning_effort="")
    llm.complete("ping")
    assert "reasoning_effort" not in seen[0]


def test_other_models_get_the_plain_request() -> None:
    llm, seen = client_for([completion("{}")], model_smart="llama3.1:8b", model_fast="")
    llm.complete("reply in JSON", json_mode=True)
    assert "reasoning_effort" not in seen[0] and "response_format" not in seen[0]


def test_a_fenced_reply_is_parsed() -> None:
    reply = '```json\n{"subject": "S", "body": "B"}\n```'
    llm, _ = client_for([completion(reply)])
    assert ask_json(llm, "P", Letter) == Letter(subject="S", body="B")


def test_a_raw_line_break_inside_the_letter_body_is_accepted() -> None:
    assert extract_json('{"subject": "S", "body": "Dear A,\nYours"}')["body"] == "Dear A,\nYours"


def test_groq_json_validate_failed_retries_once_with_a_stricter_prompt() -> None:
    llm, seen = client_for(
        [
            groq_error(400, "json_validate_failed", "Failed to generate JSON"),
            completion('{"subject": "S", "body": "B"}'),
        ]
    )
    assert ask_json(llm, "P", Letter).subject == "S"
    assert len(seen) == 2
    assert "ONLY one valid JSON object" in seen[1]["messages"][0]["content"]
    assert seen[1]["response_format"] == {"type": "json_object"}  # JSON mode stays on


def test_invalid_json_twice_is_a_structured_error_after_one_retry() -> None:
    llm, seen = client_for([completion("Sure! Here is the letter."), completion("Dear Sir,")])
    with pytest.raises(StructuredOutputError):
        ask_json(llm, "P", Letter)
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [(404, "model_not_found"), (401, "invalid_api_key"), (403, "permission_denied")],
)
def test_permanent_errors_fail_fast_with_one_request(
    status: int, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    llm, seen = client_for([groq_error(status, code, f"echo {SECRET_PROMPT}")])
    with caplog.at_level(logging.ERROR, "uvicorn.error"), pytest.raises(LLMMisconfigured) as err:
        llm.complete(SECRET_PROMPT)
    assert len(seen) == 1  # never retried
    assert "misconfigured" in str(err.value)
    assert SECRET_PROMPT not in str(err.value)
    line = caplog.text
    assert "misconfigured" in line and code in line and "openai/gpt-oss-120b" in line
    assert SECRET_PROMPT not in line  # the operator's log has no case text


def test_a_decommissioned_model_is_misconfigured() -> None:
    llm, seen = client_for(
        [groq_error(400, "model_decommissioned"), groq_error(400, "model_decommissioned")],
        model_smart="llama-3.3-70b-versatile",
    )
    with pytest.raises(LLMMisconfigured):
        llm.complete("hi")
    assert len(seen) == 1  # no extras were sent, so nothing to retry without


def test_an_endpoint_that_refuses_the_extras_is_retried_plain_for_that_call_only() -> None:
    """One provider 400 (maybe about that one prompt) must not switch JSON mode off for good."""
    llm, seen = client_for(
        [groq_error(400, "unsupported_parameter"), completion("one"), completion("two")]
    )
    assert llm.complete("hi", json_mode=True) == "one"
    assert "reasoning_effort" in seen[0]
    assert "reasoning_effort" not in seen[1] and "response_format" not in seen[1]
    assert llm.complete("again", json_mode=True) == "two"
    assert "reasoning_effort" in seen[2] and "response_format" in seen[2]


def test_429_is_still_retried_and_500_is_not_misconfiguration() -> None:
    llm, seen = client_for(
        [httpx.Response(429, json={"error": {"message": "slow"}}), completion("ok")]
    )
    assert llm.complete("hi") == "ok" and len(seen) == 2
    llm, seen = client_for([httpx.Response(500, json={"error": {"message": "oops"}})])
    with pytest.raises(openai.InternalServerError):
        llm.complete("hi")
    assert len(seen) == 1
