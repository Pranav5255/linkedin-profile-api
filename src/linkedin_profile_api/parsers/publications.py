from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import date_range, first_url, format_date, is_group_entity, nested_name, text
from linkedin_profile_api.schemas.profile import Publication
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_publications(payload: Any, visibility: Visibility) -> tuple[list[Publication], SectionState]:
    items: list[Publication] = []
    seen: set[tuple[str, str]] = set()
    try:
        entities = collect_by_type(payload, "Publication", "profile.Publication")
        for entity in entities:
            if is_group_entity(entity):
                continue
            title = text(entity.get("name"), entity.get("title"))
            if not title:
                continue
            url = first_url(entity.get("url"), entity.get("publicationUrl"))
            start, _end, _current = date_range(entity)
            published = format_date(
                entity.get("publishedOn")
                or entity.get("publishedDate")
                or entity.get("date")
                or entity.get("issueDate")
            ) or start
            key = (title.casefold(), url or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Publication(
                    title=title,
                    publisher=text(
                        entity.get("publisher"),
                        entity.get("publisherName"),
                        nested_name(entity.get("publisherV2")),
                    ),
                    date=published,
                    url=url,
                    description=text(entity.get("description")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
