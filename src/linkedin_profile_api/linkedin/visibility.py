from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import first_profile_entity
from linkedin_profile_api.schemas.response import SectionState, Visibility

REDACTION_SENTINELS = frozenset({"linkedin member", "a linkedin member", "linkedin member."})


def _text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def detect_visibility(payload: Any) -> Visibility:
    entity = first_profile_entity(payload) or {}
    first = _text(entity.get("firstName"), entity.get("firstNameV2"))
    last = _text(entity.get("lastName"), entity.get("lastNameV2"))
    full = _text(
        entity.get("publicFullName"),
        " ".join(part for part in (first, last) if part),
        entity.get("fullName"),
    ).strip()
    lowered = full.lower()
    if lowered in REDACTION_SENTINELS or (
        first.lower() == "linkedin" and last.lower() == "member"
    ):
        return Visibility.OUT_OF_NETWORK
    if entity.get("memorialized") or entity.get("profileStatefulProfile") == "PRIVATE":
        return Visibility.LIMITED
    if full:
        return Visibility.FULL
    return Visibility.UNKNOWN


def section_state_for_visibility(visibility: Visibility, items: list[Any]) -> SectionState:
    if visibility in {Visibility.OUT_OF_NETWORK, Visibility.LIMITED}:
        if not items:
            return SectionState.INACCESSIBLE
    if items:
        return SectionState.AVAILABLE
    return SectionState.EMPTY


def is_redacted_name(first_name: str | None, last_name: str | None, full_name: str | None) -> bool:
    full = (full_name or "").strip().lower()
    if full in REDACTION_SENTINELS:
        return True
    return (first_name or "").strip().lower() == "linkedin" and (last_name or "").strip().lower() == "member"
