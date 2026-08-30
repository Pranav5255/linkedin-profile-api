from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import format_date, image_url, text
from linkedin_profile_api.schemas.profile import Certification
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_certifications(payload: Any, visibility: Visibility) -> tuple[list[Certification], SectionState]:
    items: list[Certification] = []
    try:
        for entity in collect_by_type(payload, "Certification", "profile.Certification"):
            name = text(entity.get("name"), entity.get("title"))
            if not name:
                continue
            items.append(
                Certification(
                    name=name,
                    issuer=text(
                        entity.get("authority"),
                        entity.get("companyName"),
                        (entity.get("company") or {}).get("name") if isinstance(entity.get("company"), dict) else None,
                    ),
                    issued=format_date(entity.get("timePeriod", {}).get("start") if isinstance(entity.get("timePeriod"), dict) else entity.get("issuedOn")),
                    expires=format_date(entity.get("timePeriod", {}).get("end") if isinstance(entity.get("timePeriod"), dict) else entity.get("expirationDate")),
                    credential_id=text(entity.get("licenseNumber"), entity.get("credentialId")),
                    credential_url=text(entity.get("url"), entity.get("credentialUrl")),
                    logo=image_url(entity.get("companyLogo") or entity.get("logo")),
                )
            )
    except Exception:
        return [], SectionState.FAILED
    return items, section_state_for_visibility(visibility, items)
