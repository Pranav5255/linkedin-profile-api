from __future__ import annotations

from typing import Any

from linkedin_profile_api.linkedin.profile_urn import normalize_profile_urn
from linkedin_profile_api.linkedin.url import canonical_profile_url
from linkedin_profile_api.linkedin.urn_resolver import first_profile_entity
from linkedin_profile_api.linkedin.visibility import is_redacted_name
from linkedin_profile_api.parsers._common import image_url, industry_name, location_text, normalize_person_name, text
from linkedin_profile_api.schemas.profile import Profile, ProfileImage
from linkedin_profile_api.schemas.response import Visibility


def parse_top_card(payload: Any, slug: str, visibility: Visibility) -> Profile:
    entity = first_profile_entity(payload, slug) or {}
    first = normalize_person_name(text(entity.get("firstName"), entity.get("firstNameV2")))
    last = normalize_person_name(text(entity.get("lastName"), entity.get("lastNameV2")))
    if first and last:
        joined = f"{first}, {last}" if "," in last else f"{first} {last}"
    else:
        joined = first or last
    full = normalize_person_name(text(entity.get("publicFullName"), joined))
    if is_redacted_name(first, last, full):
        visibility = Visibility.OUT_OF_NETWORK
    location = location_text(
        entity.get("geoLocationName"),
        entity.get("locationName"),
        entity.get("address"),
        entity.get("geoLocation"),
        entity.get("location"),
    )
    about = text(entity.get("summary"), entity.get("multiLocaleSummary"), entity.get("headlineAbout"), entity.get("about"))
    public_id = text(entity.get("publicIdentifier"), slug) or slug
    images: list[ProfileImage] = []
    picture = image_url(entity.get("profilePicture") or entity.get("displayPicture"))
    if picture:
        images.append(ProfileImage(url=picture, category="profile"))
    background = image_url(entity.get("backgroundPicture") or entity.get("backgroundImage"))
    return Profile(
        public_identifier=public_id,
        profile_url=canonical_profile_url(public_id),
        visibility=visibility.value,
        first_name=None if visibility == Visibility.OUT_OF_NETWORK else first,
        last_name=None if visibility == Visibility.OUT_OF_NETWORK else last,
        full_name=None if visibility == Visibility.OUT_OF_NETWORK else full,
        headline=text(entity.get("headline")),
        location=location,
        industry=industry_name(entity.get("industry"), entity.get("industryName"), entity.get("industryV2")),
        about=about,
        profile_images=images,
        background_image=ProfileImage(url=background, category="background") if background else None,
    )


def extract_entity_urn(payload: Any) -> str | None:
    entity = first_profile_entity(payload) or {}
    for key in ("entityUrn", "urn", "profileUrn"):
        value = entity.get(key)
        if isinstance(value, str):
            normalized = normalize_profile_urn(value)
            if normalized:
                return normalized
    return None
