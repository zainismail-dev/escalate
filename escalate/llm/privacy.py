"""Tell the UI when complaint data would leave the user's machine."""

from urllib.parse import urlparse

from escalate.config import Settings, get_settings

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "ollama", "host.docker.internal"}


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".local")


def is_cloud(settings: Settings | None = None) -> bool:
    """True when the warning is on and LLM_BASE_URL points somewhere other than this machine."""
    s = settings or get_settings()
    return s.cloud_privacy_warning and not is_local_url(s.llm_base_url)
