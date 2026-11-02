"""One OpenAI-compatible client for Ollama, Groq, Gemini, OpenRouter or any paid API."""

import logging
import time
from collections.abc import Callable
from typing import Any, Literal, Protocol

import openai

from escalate.config import Settings, get_settings
from escalate.netguard import check_url

Slot = Literal["smart", "fast"]

log = logging.getLogger("uvicorn.error")

# Reasoning models that take `reasoning_effort` and JSON mode. Other endpoints may refuse both, so
# they only ever get the plain request. Matched anywhere in the name: "openai/gpt-oss-20b" on
# Groq, "gpt-oss:20b" on Ollama.
REASONING_MODELS = ("gpt-oss",)
# A 400 about one request's size or output, not about the model or the key.
_NOT_CONFIG = {"context_length_exceeded"}
_INVALID_JSON = "json_validate_failed"  # Groq's JSON mode refused what the model generated


class LLMNotConfigured(RuntimeError):
    pass


class LLMMisconfigured(RuntimeError):
    """A permanent error (unknown model, bad key): retrying cannot help, the operator must fix it.

    The message is for the user; the status and error code go to the operator's log."""

    def __init__(self, status: int) -> None:
        super().__init__("The AI service is misconfigured. Nothing was sent.")
        self.status = status


class LLMBadOutput(Exception):
    """The endpoint answered, but with nothing usable: no text, or JSON its JSON mode refused."""


class LLM(Protocol):
    """What the agent needs from a model. The real client and the test fake both satisfy it."""

    def complete(self, prompt: str, slot: Slot = "smart", json_mode: bool = False) -> str: ...


def is_reasoning_model(model: str) -> bool:
    return any(name in model.lower() for name in REASONING_MODELS)


def _error_code(exc: openai.APIStatusError) -> str:
    """Groq and OpenAI put it at body.code or body.error.code. Codes only: never the message."""
    body = exc.body if isinstance(exc.body, dict) else {}
    inner = body.get("error")
    code = (inner if isinstance(inner, dict) else body).get("code")
    return str(code) if code else ""


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
        if client is None:  # never connect to metadata / unlisted private addresses
            check_url(self.settings.llm_base_url, "LLM_BASE_URL")
        self._client = client or openai.OpenAI(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key or "none",
            max_retries=0,  # we handle 429 ourselves
            timeout=300,
            # Never follow redirects: a 307 from an allowed endpoint could send the request (and
            # the API key) to an internal address that check_url would have refused.
            http_client=openai.DefaultHttpx2Client(follow_redirects=False, timeout=300),
        )
        self.max_rate_retries = max_rate_retries
        self.base_delay = base_delay
        self._sleep = sleep
        self._extras_refused = False  # this endpoint said 400 to reasoning_effort or JSON mode

    def model_for(self, slot: Slot) -> str:
        model = self.settings.model_smart if slot == "smart" else self.settings.model_fast_or_smart
        if not model or model.startswith("<"):
            raise LLMNotConfigured("No model configured: set MODEL_SMART (and MODEL_FAST) in .env")
        return model

    def _extras(self, model: str, json_mode: bool) -> dict[str, Any]:
        if self._extras_refused or not is_reasoning_model(model):
            return {}
        extras: dict[str, Any] = {}
        if self.settings.llm_reasoning_effort:
            extras["reasoning_effort"] = self.settings.llm_reasoning_effort
        if json_mode:
            extras["response_format"] = {"type": "json_object"}
        return extras

    def _create(self, model: str, prompt: str, extras: dict[str, Any]) -> str:
        """The reply text. Only `message.content`: a reasoning model's thoughts stay out of it."""
        resp = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            **extras,
        )
        content = resp.choices[0].message.content if resp.choices else None
        if not content or not content.strip():
            raise LLMBadOutput("the model returned no text")
        return content

    def _classify_status_error(
        self, exc: openai.APIStatusError, model: str, slot: Slot
    ) -> Exception:
        """What a non-429 error means. Logs the permanent ones for the operator: status and error
        code only, the response body may repeat the prompt."""
        code = _error_code(exc)
        if exc.status_code == 400 and code == _INVALID_JSON:
            return LLMBadOutput("the model's JSON was refused by the endpoint")
        permanent = exc.status_code in (400, 401, 403, 404, 422) and code not in _NOT_CONFIG
        if not permanent:
            return exc
        log.error(
            "AI service misconfigured: HTTP %s (%s) for model %s (slot %s). "
            "Check MODEL_SMART, MODEL_FAST, LLM_BASE_URL and LLM_API_KEY.",
            exc.status_code,
            code or "no error code",
            model,
            slot,
        )
        return LLMMisconfigured(exc.status_code)

    def complete(self, prompt: str, slot: Slot = "smart", json_mode: bool = False) -> str:
        model = self.model_for(slot)
        for attempt in range(self.max_rate_retries + 1):
            extras = self._extras(model, json_mode)
            try:
                return self._create(model, prompt, extras)
            except openai.RateLimitError:
                if attempt == self.max_rate_retries:
                    raise
                self._sleep(self.base_delay * (2**attempt))
            except openai.BadRequestError as exc:
                retry_plain = extras and _error_code(exc) not in (_INVALID_JSON, *_NOT_CONFIG)
                if not retry_plain:
                    raise self._classify_status_error(exc, model, slot) from exc
                # Maybe the extras it refused (an unknown model fails the plain request too).
                self._extras_refused = True
                log.warning("LLM endpoint refused optional parameters (HTTP 400); not sent again")
            except openai.APIStatusError as exc:
                raise self._classify_status_error(exc, model, slot) from exc
        raise AssertionError("unreachable")
