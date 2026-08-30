from __future__ import annotations

import re
from typing import Any

_COMPANY_URN_RE = re.compile(r"(?:fsd_company|company):([^,\s/]+)", re.IGNORECASE)


def text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, dict):
            nested = (
                value.get("text")
                or value.get("value")
                or value.get("localized")
                or value.get("defaultLocalizedName")
                or value.get("defaultLocalizedNameWithoutCountryName")
            )
            if isinstance(nested, dict):
                nested = next(iter(nested.values()), None)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def format_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    year = value.get("year")
    month = value.get("month")
    if year and month:
        return f"{int(year):04d}-{int(month):02d}"
    if year:
        return f"{int(year):04d}"
    return None


def date_range(entity: dict[str, Any]) -> tuple[str | None, str | None, bool]:
    span = entity.get("dateRange") or entity.get("timePeriod") or {}
    if not isinstance(span, dict):
        return None, None, False
    start = format_date(span.get("start") or span.get("startDate"))
    end = format_date(span.get("end") or span.get("endDate"))
    current = bool(entity.get("present") or span.get("end") is None)
    return start, end, current


def company_url(company_id: str | None, company: Any = None) -> str | None:
    if isinstance(company, dict):
        direct = first_url(company.get("url"))
        if direct:
            return direct
        vanity = text(company.get("universalName"), company.get("vanityName"))
        if vanity:
            return f"https://www.linkedin.com/company/{vanity}/"
    if not company_id:
        return None
    if str(company_id).startswith("http"):
        return str(company_id)
    match = _COMPANY_URN_RE.search(str(company_id))
    if match:
        return f"https://www.linkedin.com/company/{match.group(1)}/"
    if "urn:" in str(company_id):
        return None
    return f"https://www.linkedin.com/company/{company_id}/"


def normalize_person_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" \t,;")
    return cleaned or None


def location_text(*values: Any) -> str | None:
    return _location_text(values, set())


def _location_text(values: tuple[Any, ...], seen: set[int]) -> str | None:
    for value in values:
        if isinstance(value, dict):
            marker = id(value)
            if marker in seen:
                continue
            seen.add(marker)
        direct = text(value)
        if direct:
            return direct
        if isinstance(value, dict):
            nested = _location_text(
                (
                    value.get("geoLocationName"),
                    value.get("locationName"),
                    value.get("defaultLocalizedName"),
                    value.get("geo"),
                    value.get("location"),
                ),
                seen,
            )
            if nested:
                return nested
    return None


def industry_name(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, list):
            for item in value:
                name = industry_name(item)
                if name:
                    return name
            continue
        if isinstance(value, dict):
            direct = text(value.get("name"), value.get("localizedName"), nested_name(value))
            if direct:
                return direct
            for item in value.values():
                if isinstance(item, dict):
                    name = industry_name(item)
                    if name:
                        return name
            continue
        direct = text(value)
        if direct:
            return direct
    return None


def is_group_entity(entity: dict[str, Any]) -> bool:
    type_name = str(entity.get("$type") or entity.get("_type") or "").lower()
    return "group" in type_name


def humanize_token(value: str | None) -> str | None:
    if not value:
        return None
    if "_" in value or value.isupper():
        return value.replace("_", " ").title()
    return value


def first_url(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.startswith("http"):
            return value
        if isinstance(value, dict):
            nested = first_url(
                value.get("url"),
                value.get("localizedUrl"),
                value.get("uri"),
                value.get("href"),
            )
            if nested:
                return nested
    return None


def nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return text(value)
    return text(value.get("name"), value.get("localizedName"), value.get("title"))


def image_url(node: Any) -> str | None:
    if isinstance(node, str) and node.startswith("http"):
        return node
    if not isinstance(node, dict):
        return None
    vector = node.get("vectorImage")
    reference = node.get("displayImageReference")
    if vector is None and isinstance(reference, dict):
        vector = reference.get("vectorImage")
    if not isinstance(vector, dict):
        vector = node
    root = vector.get("rootUrl") if isinstance(vector, dict) else None
    artifacts = vector.get("artifacts") if isinstance(vector, dict) else None
    if isinstance(root, str) and isinstance(artifacts, list) and artifacts:
        largest = artifacts[-1]
        segment = largest.get("fileIdentifyingUrlPathSegment") if isinstance(largest, dict) else None
        if isinstance(segment, str):
            return f"{root}{segment}"
    for key in ("url", "src", "rootUrl"):
        value = node.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None
