from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import text
from linkedin_profile_api.schemas.profile import Skill
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_skills(payload: Any, visibility: Visibility) -> tuple[list[Skill], SectionState]:
    items: list[Skill] = []
    try:
        for entity in collect_by_type(payload, "Skill", "profile.Skill"):
            name = text(entity.get("name"), entity.get("skillName"), entity.get("title"))
            if not name:
                continue
            related: list[str] = []
            raw_related = entity.get("relatedExperience") or entity.get("insight")
            if isinstance(raw_related, list):
                for entry in raw_related:
                    label = text(entry if not isinstance(entry, dict) else entry.get("name") or entry.get("title"))
                    if label:
                        related.append(label)
            items.append(
                Skill(
                    name=name,
                    endorsement_count=_as_int(entity.get("endorsementCount") or entity.get("numEndorsements")),
                    related_experience=related,
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
