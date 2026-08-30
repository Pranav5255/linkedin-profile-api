from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import date_range, image_url, text
from linkedin_profile_api.schemas.profile import Education
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_education(payload: Any, visibility: Visibility) -> tuple[list[Education], SectionState]:
    items: list[Education] = []
    try:
        for entity in collect_by_type(payload, "Education", "profile.Education"):
            school = text(
                entity.get("schoolName"),
                (entity.get("school") or {}).get("name") if isinstance(entity.get("school"), dict) else None,
                entity.get("name"),
            )
            if not school:
                continue
            start, end, _current = date_range(entity)
            items.append(
                Education(
                    school=school,
                    degree=text(entity.get("degreeName"), entity.get("degree")),
                    field=text(entity.get("fieldOfStudy"), entity.get("field")),
                    start_date=start,
                    end_date=end,
                    grade=text(entity.get("grade")),
                    activities=text(entity.get("activities"), entity.get("activitiesAndSocieties")),
                    description=text(entity.get("description"), entity.get("notes")),
                    logo=image_url(entity.get("schoolLogo") or entity.get("logo")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
