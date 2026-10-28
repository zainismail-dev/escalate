"""A scripted, offline stand-in for the LLM. Used by every unit test."""

import json
from collections.abc import Callable
from typing import Any

from escalate.llm.client import Slot

Reply = str | dict[str, Any] | Exception
Handler = Callable[[str, Slot], Reply]


class FakeLLM:
    """Replies come from, in order: a queue of scripted replies, then `rules`, then `handler`.

    - `script`: replies returned one per call, first in first out.
    - `rules`: (substring, reply) pairs; the first whose substring is in the prompt wins.
    - `handler`: a function of (prompt, slot) for anything else.
    A dict reply is sent as JSON; an Exception reply is raised.
    """

    def __init__(
        self,
        script: list[Reply] | None = None,
        rules: list[tuple[str, Reply | Handler]] | None = None,
        handler: Handler | None = None,
    ) -> None:
        self.script = list(script or [])
        self.rules = list(rules or [])
        self.handler = handler
        self.calls: list[tuple[str, Slot]] = []

    def complete(self, prompt: str, slot: Slot = "smart") -> str:
        self.calls.append((prompt, slot))
        reply = self._pick(prompt, slot)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, dict):
            return json.dumps(reply)
        return reply

    def _pick(self, prompt: str, slot: Slot) -> Reply:
        if self.script:
            return self.script.pop(0)
        for needle, reply in self.rules:
            if needle in prompt:
                return reply(prompt, slot) if callable(reply) else reply
        if self.handler:
            return self.handler(prompt, slot)
        raise AssertionError(f"FakeLLM has no reply for prompt: {prompt[:200]!r}")

    def prompts_containing(self, needle: str) -> list[str]:
        return [p for p, _ in self.calls if needle in p]
