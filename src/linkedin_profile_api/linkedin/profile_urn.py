from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

PROFILE_URN_RE = re.compile(r"urn:li:fsd_profile:(ACo[A-Za-z0-9_-]{8,})")
MINI_PROFILE_URN_RE = re.compile(r"urn:li:fs_miniProfile:(ACo[A-Za-z0-9_-]{8,})")
PUBLIC_IDENTIFIER_RE = re.compile(r'"publicIdentifier"\s*:\s*"([^"]+)"')
VANITY_NAME_RE = re.compile(r'"vanityName"\s*:\s*"([^"]+)"')
PROFILE_PATH_RE = re.compile(
    r"https://(?:www\.)?linkedin\.com/in/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
IDENTITY_URN_SUFFIX_RE = re.compile(
    r"/(?:urn:li:fsd_profile:[A-Za-z0-9_-]+|urn%3Ali%3Afsd_profile%3A[A-Za-z0-9_-]+)/?$",
    re.IGNORECASE,
)
IDENTITY_COLLECTION_PATH = "/voyager/api/identity/dash/profiles"
_PAIR_WINDOW = 8000


def normalize_profile_urn(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    text = _unescape_blob(value)
    # Prefer the last ACo id so a doubled prefix like
    # urn:li:fsd_profile:urn:li:fsd_profile:ACo... does not capture "urn".
    matches = PROFILE_URN_RE.findall(text)
    if not matches:
        return None
    return f"urn:li:fsd_profile:{matches[-1]}"


def identity_profile_path(urn: str) -> str:
    normalized = normalize_profile_urn(urn)
    if normalized is None:
        raise ValueError("A LinkedIn fsd_profile URN is required.")
    return f"{IDENTITY_COLLECTION_PATH}/{normalized}"


def normalize_identity_collection_path(path: str) -> str:
    cleaned = unquote(path or "")
    cleaned = IDENTITY_URN_SUFFIX_RE.sub("", cleaned)
    if cleaned.endswith("/") and cleaned != "/":
        cleaned = cleaned.rstrip("/")
    return cleaned or IDENTITY_COLLECTION_PATH


def extract_profile_urn_from_html(html: str, slug: str) -> str | None:
    if not html or not slug:
        return None
    text = _unescape_blob(html)
    paired = _urn_near_slug(text, slug)
    if paired:
        return paired
    return None


def extract_profile_urn_from_payload(payload: Any, slug: str | None = None) -> str | None:
    if slug:
        paired = _walk_for_slug_urn(payload, slug.lower())
        if paired:
            return paired
    return _first_profile_urn(payload)


def _unescape_blob(raw: str) -> str:
    return (
        raw.replace("&quot;", '"')
        .replace("&#34;", '"')
        .replace("\\u003a", ":")
        .replace("\\u002d", "-")
        .replace("\\x3a", ":")
        .replace("%3A", ":")
        .replace("%3a", ":")
        .replace("\\/", "/")
    )


def _urn_near_slug(text: str, slug: str) -> str | None:
    lowered = slug.lower()
    best: str | None = None
    best_distance = 10**9
    anchors: list[re.Match[str]] = []
    anchors.extend(match for match in PUBLIC_IDENTIFIER_RE.finditer(text) if match.group(1).lower() == lowered)
    anchors.extend(match for match in VANITY_NAME_RE.finditer(text) if match.group(1).lower() == lowered)
    anchors.extend(match for match in PROFILE_PATH_RE.finditer(text) if match.group(1).lower() == lowered)
    for anchor in anchors:
        start = max(0, anchor.start() - _PAIR_WINDOW)
        end = min(len(text), anchor.end() + _PAIR_WINDOW)
        window = text[start:end]
        for pattern in (PROFILE_URN_RE, MINI_PROFILE_URN_RE):
            for urn_match in pattern.finditer(window):
                distance = abs((start + urn_match.start()) - anchor.start())
                if distance < best_distance:
                    best_distance = distance
                    best = f"urn:li:fsd_profile:{urn_match.group(1)}"
    return best


def _walk_for_slug_urn(node: Any, slug: str) -> str | None:
    stack: list[Any] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
            continue
        if not isinstance(current, dict):
            continue
        public_id = current.get("publicIdentifier") or current.get("vanityName")
        if isinstance(public_id, str) and public_id.lower() == slug:
            for key in ("entityUrn", "urn", "profileUrn"):
                normalized = normalize_profile_urn(current.get(key) if isinstance(current.get(key), str) else None)
                if normalized:
                    return normalized
        stack.extend(current.values())
    return None


def _first_profile_urn(node: Any) -> str | None:
    stack: list[Any] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
            continue
        if isinstance(current, str):
            normalized = normalize_profile_urn(current)
            if normalized:
                return normalized
            continue
        if isinstance(current, dict):
            stack.extend(current.values())
    return None
