from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import date_range, first_url, is_group_entity, text
from linkedin_profile_api.schemas.profile import Project
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_projects(payload: Any, visibility: Visibility) -> tuple[list[Project], SectionState]:
    items: list[Project] = []
    seen: set[tuple[str, str]] = set()
    try:
        entities = collect_by_type(payload, "identity.profile.Project", "profile.Project")
        for entity in entities:
            if is_group_entity(entity):
                continue
            name = text(entity.get("title"), entity.get("name"))
            if not name:
                continue
            start, end, _current = date_range(entity)
            url = first_url(entity.get("url"), entity.get("website"), entity.get("projectUrl"))
            key = (name.casefold(), url or start or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Project(
                    name=name,
                    description=text(entity.get("description")),
                    start_date=start,
                    end_date=end,
                    url=url,
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
