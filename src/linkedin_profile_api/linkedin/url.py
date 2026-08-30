from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from linkedin_profile_api.linkedin.exceptions import InvalidProfileUrlError

_ALLOWED_HOSTS = frozenset({"linkedin.com", "www.linkedin.com"})
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
_MAX_URL_LENGTH = 512
_ENCODED_SEPARATORS = ("%2f", "%2e", "%5c", "%00")


def parse_profile_url(raw: str, *, max_length: int = _MAX_URL_LENGTH) -> str:
    if not raw or not isinstance(raw, str):
        raise InvalidProfileUrlError("Profile URL is required.")
    candidate = raw.strip()
    if not candidate or len(candidate) > max_length:
        raise InvalidProfileUrlError("Profile URL is empty or too long.")
    lowered = candidate.lower()
    if any(token in lowered for token in _ENCODED_SEPARATORS):
        raise InvalidProfileUrlError("Profile URL contains encoded path separators.")
    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        raise InvalidProfileUrlError("Profile URL must use HTTPS.")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise InvalidProfileUrlError("Profile URL host must be linkedin.com or www.linkedin.com.")
    path = unquote(parsed.path or "")
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) < 2 or parts[0].lower() != "in":
        raise InvalidProfileUrlError("Profile URL path must start with /in/.")
    slug = parts[1]
    if ".." in slug or "/" in slug or "\\" in slug:
        raise InvalidProfileUrlError("Profile slug failed traversal checks.")
    if not _SLUG_RE.fullmatch(slug):
        raise InvalidProfileUrlError("Profile slug is empty, oversized, or malformed.")
    return slug


def canonical_profile_url(slug: str) -> str:
    return f"https://www.linkedin.com/in/{slug}/"
