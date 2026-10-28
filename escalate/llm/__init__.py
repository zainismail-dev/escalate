"""LLM access. Code asks `get_llm()` for the model; tests swap in a fake with `set_llm()`."""

from escalate.llm.client import LLM, LLMClient, Slot

_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def set_llm(llm: LLM | None) -> None:
    global _llm
    _llm = llm


__all__ = ["LLM", "LLMClient", "Slot", "get_llm", "set_llm"]
