"""Outbound-connection guard for user-configurable endpoints (LLM_BASE_URL, SMTP_HOST).

Always blocked: link-local and cloud-metadata addresses (169.254.0.0/16, fe80::/10,
fd00:ec2::254), whatever the name resolves to. Private and loopback addresses are allowed only
for hosts listed in LOCAL_ENDPOINT_HOSTS (the local model or mail relay you meant to use).
Checked when settings are saved and again right before connecting.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

from escalate.config import get_settings

IP = ipaddress.IPv4Address | ipaddress.IPv6Address

ALWAYS_BLOCKED = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, incl. 169.254.169.254 metadata
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS IPv6 metadata
    ipaddress.ip_network("0.0.0.0/8"),
]


class UnsafeEndpoint(ValueError):
    """The endpoint points somewhere Escalate must not connect to."""


def _local_hosts() -> set[str]:
    raw = get_settings().local_endpoint_hosts
    return {h.strip().lower().strip("[]") for h in raw.split(",") if h.strip()}


def _resolve(host: str) -> list[IP]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return []  # unresolvable now: nothing to connect to; checked again before connecting
    return [ipaddress.ip_address(str(info[4][0]).split("%")[0]) for info in infos]


def check_host(host: str, what: str) -> None:
    name = host.strip().lower().strip("[]")
    if not name:
        raise UnsafeEndpoint(f"{what}: missing host")
    for ip in _resolve(name):
        mapped = getattr(ip, "ipv4_mapped", None)
        target: IP = mapped or ip
        if any(target in net for net in ALWAYS_BLOCKED):
            raise UnsafeEndpoint(f"{what}: {host} is a link-local or cloud-metadata address")
        local = target.is_private or target.is_loopback or target.is_reserved
        if (local or target.is_unspecified or target.is_multicast) and name not in _local_hosts():
            raise UnsafeEndpoint(
                f"{what}: {host} is a private or loopback address; to use a local endpoint, add "
                "it to LOCAL_ENDPOINT_HOSTS"
            )


def check_url(url: str, what: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeEndpoint(f"{what}: must be an http(s) URL")
    check_host(parts.hostname, what)


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()
