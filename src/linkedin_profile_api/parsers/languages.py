from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import humanize_token, text
from linkedin_profile_api.schemas.profile import Language
from linkedin_profile_api.schemas.response import SectionState, Visibility

_PROFICIENCY = {
    "ELEMENTARY": "Elementary",
    "LIMITED_WORKING": "Limited working",
    "PROFESSIONAL_WORKING": "Professional working",
    "FULL_PROFESSIONAL": "Full professional",
    "NATIVE_OR_BILINGUAL": "Native or bilingual",
}


def parse_languages(payload: Any, visibility: Visibility) -> tuple[list[Language], SectionState]:
    items: list[Language] = []
    seen: set[str] = set()
    try:
        for entity in collect_by_type(payload, "Language", "profile.Language"):
            name = text(entity.get("name"), entity.get("language"), entity.get("title"))
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Language(
                    language=name,
                    proficiency=_proficiency(entity.get("proficiency") or entity.get("proficiencyLevel")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)


def _proficiency(value: Any) -> str | None:
    raw = text(value)
    if not raw:
        return None
    return _PROFICIENCY.get(raw.upper(), humanize_token(raw))
