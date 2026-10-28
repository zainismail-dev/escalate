"""Ask for JSON, validate it with Pydantic, and retry with the error when a small model slips."""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from escalate.llm.client import LLM, Slot

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class StructuredOutputError(Exception):
    """The model never produced valid JSON for the requested schema."""


def extract_json(text: str) -> Any:
    """Pull the first JSON object out of a model reply, repairing common slips."""
    candidates = [m.strip() for m in _FENCE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    candidates.append(text.strip())
    for cand in candidates:
        for attempt in (cand, _TRAILING_COMMA.sub(r"\1", cand)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object found in the reply")


def ask_json[T: BaseModel](
    llm: LLM, prompt: str, model_cls: type[T], slot: Slot = "smart", retries: int = 2
) -> T:
    """Return a validated `model_cls`; on bad output retry up to `retries` times with the error."""
    current = prompt
    last_error = ""
    for _ in range(retries + 1):
        reply = llm.complete(current, slot=slot)
        try:
            return model_cls.model_validate(extract_json(reply))
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)
            current = (
                f"{prompt}\n\nYour previous reply was not valid. Error:\n{last_error}\n"
                "Reply again with ONLY the corrected JSON object, no other text."
            )
    raise StructuredOutputError(last_error)
