from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import date_range, format_date, is_group_entity, nested_name, text
from linkedin_profile_api.schemas.profile import Honor
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_honors(payload: Any, visibility: Visibility) -> tuple[list[Honor], SectionState]:
    items: list[Honor] = []
    seen: set[tuple[str, str, str]] = set()
    try:
        entities = collect_by_type(payload, "HonorAward", "profile.Honor")
        for entity in entities:
            if is_group_entity(entity):
                continue
            title = text(entity.get("title"), entity.get("name"))
            if not title:
                continue
            issuer = text(
                entity.get("issuer"),
                entity.get("issuerName"),
                nested_name(entity.get("issuerV2")),
            )
            start, _end, _current = date_range(entity)
            issued = format_date(
                entity.get("issuedOn") or entity.get("issueDate") or entity.get("date")
            ) or start
            key = (title.casefold(), (issuer or "").casefold(), issued or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Honor(
                    title=title,
                    issuer=issuer,
                    date=issued,
                    description=text(entity.get("description")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
