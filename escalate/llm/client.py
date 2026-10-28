"""One OpenAI-compatible client for Ollama, Groq, Gemini, OpenRouter or any paid API."""

import time
from collections.abc import Callable
from typing import Literal, Protocol

import openai

from escalate.config import Settings, get_settings

Slot = Literal["smart", "fast"]


class LLMNotConfigured(RuntimeError):
    pass


class LLM(Protocol):
    """What the agent needs from a model. The real client and the test fake both satisfy it."""

    def complete(self, prompt: str, slot: Slot = "smart") -> str: ...


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        client: openai.OpenAI | None = None,
        max_rate_retries: int = 5,
        base_delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client or openai.OpenAI(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key or "none",
            max_retries=0,  # we handle 429 ourselves
            timeout=300,
        )
        self.max_rate_retries = max_rate_retries
        self.base_delay = base_delay
        self._sleep = sleep

    def model_for(self, slot: Slot) -> str:
        model = self.settings.model_smart if slot == "smart" else self.settings.model_fast_or_smart
        if not model or model.startswith("<"):
            raise LLMNotConfigured("No model configured: set MODEL_SMART (and MODEL_FAST) in .env")
        return model

    def complete(self, prompt: str, slot: Slot = "smart") -> str:
        model = self.model_for(slot)
        for attempt in range(self.max_rate_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                return resp.choices[0].message.content or ""
            except openai.RateLimitError:
                if attempt == self.max_rate_retries:
                    raise
                self._sleep(self.base_delay * (2**attempt))
        raise AssertionError("unreachable")
