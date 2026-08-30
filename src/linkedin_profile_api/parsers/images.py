from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.urn_resolver import collect_by_type
from linkedin_profile_api.linkedin.visibility import section_state_for_visibility
from linkedin_profile_api.parsers._common import image_url
from linkedin_profile_api.schemas.profile import ProfileImage
from linkedin_profile_api.schemas.response import SectionState, Visibility


def parse_images(payload: Any, visibility: Visibility) -> tuple[list[ProfileImage], SectionState]:
    items: list[ProfileImage] = []
    try:
        for entity in collect_by_type(payload, "VectorImage", "ImageViewModel", "profile.Profile"):
            url = image_url(entity.get("profilePicture") or entity.get("vectorImage") or entity)
            if not url:
                continue
            artifacts = []
            vector = entity.get("vectorImage") if isinstance(entity.get("vectorImage"), dict) else entity
            if isinstance(vector, dict):
                artifacts = vector.get("artifacts") or []
            width = height = None
            if artifacts and isinstance(artifacts[-1], dict):
                width = artifacts[-1].get("width")
                height = artifacts[-1].get("height")
            items.append(ProfileImage(url=url, width=width, height=height, category="profile"))
    except Exception:
        return [], SectionState.FAILED
    unique: list[ProfileImage] = []
    seen: set[str] = set()
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)
    return unique, section_state_for_visibility(visibility, unique)
