"""LLM access. Code asks `get_llm()` for the model; tests swap in a fake with `set_llm()`.

Hosted mode: the server's provider only (LLM_* from the environment), and every call counts
against the user's and the beta's daily AI limits (escalate/llm/quota.py)."""

from escalate.config import get_settings
from escalate.llm.client import LLM, LLMClient, Slot

_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    if get_settings().hosted:
        from escalate.llm.quota import MeteredLLM

        return MeteredLLM(_llm)
    return _llm


def set_llm(llm: LLM | None) -> None:
    global _llm
    _llm = llm


__all__ = ["LLM", "LLMClient", "Slot", "get_llm", "set_llm"]
