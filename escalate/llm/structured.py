"""Ask for JSON, validate it with Pydantic, and retry once, more strictly, when a model slips."""

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from escalate.llm.client import LLM, LLMBadOutput, Slot

log = logging.getLogger("uvicorn.error")

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class StructuredOutputError(Exception):
    """The model never produced valid JSON for the requested schema."""

    def __init__(self, message: str, category: str = "invalid_json") -> None:
        super().__init__(message)
        self.category = category  # safe to log: says what failed, never what the model wrote


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
                # strict=False: a raw line break inside a string (a letter's body) is fine.
                return json.loads(attempt, strict=False)
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object found in the reply")


def ask_json[T: BaseModel](
    llm: LLM, prompt: str, model_cls: type[T], slot: Slot = "smart", retries: int = 1
) -> T:
    """Return a validated `model_cls`; on bad output retry `retries` times, naming the error."""
    current = prompt
    last_error = ""
    category = "invalid_json"
    for _ in range(retries + 1):
        try:
            reply = llm.complete(current, slot=slot, json_mode=True)
            return model_cls.model_validate(extract_json(reply))
        except ValidationError as exc:
            last_error, category = str(exc), "schema_mismatch"
        except (ValueError, LLMBadOutput) as exc:
            last_error, category = str(exc), "invalid_json"
        log.warning("LLM structured output rejected: %s (slot %s)", category, slot)
        current = (
            f"{prompt}\n\nYour previous reply was not valid. Error:\n{last_error}\n"
            "Reply again with ONLY one valid JSON object that matches the format above: "
            "no code fences, no comments, no text before or after it."
        )
    raise StructuredOutputError(last_error, category)
