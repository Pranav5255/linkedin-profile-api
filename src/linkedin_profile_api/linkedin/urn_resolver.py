from __future__ import annotations

from copy import deepcopy
from typing import Any

MAX_DEPTH = 8
SECTION_TYPE_NEEDLES = (
    "Position",
    "Education",
    "Skill",
    "profile.Position",
    "profile.Education",
    "profile.Skill",
    "Certification",
    "profile.Language",
    "VolunteerExperience",
    "profile.Volunteer",
    "identity.profile.Project",
    "profile.Project",
    "profile.Publication",
    "HonorAward",
    "profile.Honor",
)


def index_entities(payload: Any) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    included = []
    if isinstance(payload, dict):
        included = payload.get("included") or []
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("included"), list):
            included = list(included) + data["included"]
    if not isinstance(included, list):
        return index
    for entity in included:
        if not isinstance(entity, dict):
            continue
        for key in ("entityUrn", "urn", "entityUrn"):
            urn = entity.get(key)
            if isinstance(urn, str) and urn:
                index[urn] = entity
    return index


def resolve_graph(payload: Any, *, max_depth: int = MAX_DEPTH) -> Any:
    source = deepcopy(payload)
    index = index_entities(source)
    seen: set[str] = set()
    return _resolve(source, index, seen, 0, max_depth)


def _resolve(
    node: Any,
    index: dict[str, dict[str, Any]],
    seen: set[str],
    depth: int,
    max_depth: int,
) -> Any:
    if depth >= max_depth:
        return node
    if isinstance(node, list):
        return [_resolve(item, index, seen, depth + 1, max_depth) for item in node]
    if not isinstance(node, dict):
        return node
    resolved: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(key, str) and key.startswith("*") and isinstance(value, str):
            resolved[key[1:]] = _deref(value, index, seen, depth, max_depth)
        elif isinstance(key, str) and key.startswith("*") and isinstance(value, list):
            resolved[key[1:]] = [
                _deref(item, index, seen, depth, max_depth) if isinstance(item, str) else _resolve(item, index, seen, depth + 1, max_depth)
                for item in value
            ]
        else:
            resolved[key] = _resolve(value, index, seen, depth + 1, max_depth)
    return resolved


def _deref(
    urn: str,
    index: dict[str, dict[str, Any]],
    seen: set[str],
    depth: int,
    max_depth: int,
) -> Any:
    if urn in seen:
        return {"urn": urn, "unresolved": True, "cycle": True}
    target = index.get(urn)
    if target is None:
        return {"urn": urn, "unresolved": True}
    seen.add(urn)
    try:
        return _resolve(target, index, seen, depth + 1, max_depth)
    finally:
        seen.discard(urn)


def identity_payload_has_sections(payload: Any) -> bool:
    return bool(collect_by_type(payload, *SECTION_TYPE_NEEDLES))


def collect_by_type(payload: Any, *type_needles: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        type_name = str(node.get("$type") or node.get("_type") or "")
        if any(needle.lower() in type_name.lower() for needle in type_needles):
            key = _entity_key(node, type_name)
            if key not in seen:
                seen.add(key)
                found.append(node)
        stack.extend(node.values())
    return found


def _entity_key(node: dict[str, Any], type_name: str) -> tuple[str, str]:
    for field in ("entityUrn", "urn", "profileUrn"):
        value = node.get(field)
        if isinstance(value, str) and value:
            return ("urn", value)
    return ("id", str(id(node)))


def _is_profile_entity(node: dict[str, Any]) -> bool:
    type_name = str(node.get("$type") or node.get("_type") or "")
    if "CollectionResponse" in type_name:
        return False
    if "identity.profile.Profile" in type_name:
        return True
    return bool(node.get("publicIdentifier") and (node.get("firstName") or node.get("headline")))


def first_profile_entity(payload: Any, slug: str | None = None) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and _is_profile_entity(data):
            candidates.append(data)
        for bucket in (payload.get("elements"), data.get("elements") if isinstance(data, dict) else None):
            if isinstance(bucket, list):
                candidates.extend(item for item in bucket if isinstance(item, dict) and _is_profile_entity(item))
    candidates.extend(collect_by_type(payload, "identity.profile.Profile", "dash.identity.profile.Profile"))

    unique: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entity in candidates:
        marker = id(entity)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(entity)

    if slug:
        wanted = slug.casefold()
        for entity in unique:
            public_id = entity.get("publicIdentifier")
            if isinstance(public_id, str) and public_id.casefold() == wanted:
                return entity

    if unique:
        return max(unique, key=len)
    return None
