from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_BUNDLE_HOST_SUFFIXES = (".licdn.com",)
_ALLOWED_BUNDLE_HOSTS = frozenset({"static.licdn.com", "licdn.com"})


def is_allowed_bundle_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _ALLOWED_BUNDLE_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _ALLOWED_BUNDLE_HOST_SUFFIXES)
