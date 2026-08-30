from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import date_range, humanize_token, is_group_entity, nested_name, text
from linkedin_profile_api.schemas.profile import Volunteering
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_volunteering(payload: Any, visibility: Visibility) -> tuple[list[Volunteering], SectionState]:
    items: list[Volunteering] = []
    seen: set[tuple[str, str, str]] = set()
    try:
        entities = collect_by_type(payload, "VolunteerExperience", "profile.Volunteer")
        for entity in entities:
            if is_group_entity(entity):
                continue
            role = text(entity.get("role"), entity.get("title"))
            organization = text(
                entity.get("companyName"),
                entity.get("organizationName"),
                nested_name(entity.get("company")),
                nested_name(entity.get("organization")),
            )
            if not role:
                role = text(entity.get("name"))
            if not role and not organization:
                continue
            start, end, _current = date_range(entity)
            key = ((role or "").casefold(), (organization or "").casefold(), start or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Volunteering(
                    role=role,
                    organization=organization,
                    cause=humanize_token(text(entity.get("cause"), nested_name(entity.get("causeV2")))),
                    start_date=start,
                    end_date=end,
                    description=text(entity.get("description")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
