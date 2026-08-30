from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import company_url, date_range, image_url, is_group_entity, location_text, text
from linkedin_profile_api.schemas.profile import Experience
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_experience(payload: Any, visibility: Visibility) -> tuple[list[Experience], SectionState]:
    items: list[Experience] = []
    try:
        entities = collect_by_type(payload, "identity.profile.Position", "profile.Position")
        for entity in entities:
            type_name = str(entity.get("$type") or entity.get("_type") or "").lower()
            if is_group_entity(entity) or "volunteer" in type_name:
                continue
            title = text(entity.get("title"))
            company_node = entity.get("company") if isinstance(entity.get("company"), dict) else None
            company = text(entity.get("companyName"), (company_node or {}).get("name"))
            if not title:
                continue
            start, end, current = date_range(entity)
            company_id = text(entity.get("companyUrn"), (company_node or {}).get("entityUrn"))
            items.append(
                Experience(
                    title=title,
                    company=company,
                    company_id=company_id,
                    company_url=company_url(company_id, company_node),
                    employment_type=text(entity.get("employmentType"), entity.get("workType")),
                    location=location_text(entity.get("locationName"), entity.get("geoLocationName"), entity.get("location")),
                    start_date=start,
                    end_date=end,
                    current=current and end is None,
                    duration=text(entity.get("duration"), entity.get("durationDescription")),
                    description=text(entity.get("description")),
                    logo=image_url(entity.get("companyLogo") or entity.get("logo") or (company_node or {}).get("logo")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
