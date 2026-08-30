from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from linkedin_profile_api.linkedin.endpoints import (
    CapturedEndpoints,
    OperationSpec,
    dump_captured_endpoints,
    identity_operation_score,
    sanitize_headers,
)
from linkedin_profile_api.linkedin.profile_urn import (
    IDENTITY_COLLECTION_PATH,
    normalize_identity_collection_path,
)

_OPERATION_HINTS = (
    ("identity", ("/identity/dash/profiles", "memberidentity", "fullprofile")),
    ("experience", ("experience", "profilecomponents", "position")),
    ("education", ("education",)),
    ("skills", ("skill",)),
    ("certifications", ("certification",)),
    ("languages", ("identitydashlanguage", "profile.language")),
    ("about", ("about", "summary")),
    ("volunteering", ("volunteer", "identitydashvolunteer")),
    ("projects", ("identitydashproject", "profile.project")),
    ("publications", ("publication", "identitydashpublication")),
    ("honors", ("honoraward", "identitydashhonor", "profile.honor")),
)


def import_har(har_path: Path, output_path: Path) -> CapturedEndpoints:
    raw = json.loads(har_path.read_text(encoding="utf-8"))
    entries = raw.get("log", {}).get("entries", [])
    headers: dict[str, str] = {}
    identity_headers: dict[str, str] = {}
    operations: dict[str, OperationSpec] = {}
    scores: dict[str, int] = {}
    for entry in entries:
        request = entry.get("request") or {}
        url = request.get("url") or ""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host not in {"www.linkedin.com", "linkedin.com"}:
            continue
        if "/voyager/api/" not in parsed.path:
            continue
        merged_headers = {
            item["name"]: item["value"]
            for item in request.get("headers") or []
            if isinstance(item, dict) and item.get("name") and item.get("value")
        }
        headers.update(sanitize_headers(merged_headers))
        query = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
        query_id = query.get("queryId")
        decoration_id = query.get("decorationId")
        name = _classify_operation(parsed.path, query, url.lower())
        if name is None:
            continue
        path = parsed.path
        stored_query = {key: value for key, value in query.items() if key not in {"queryId"}}
        if name == "identity":
            path = normalize_identity_collection_path(unquote(parsed.path))
            stored_query.pop("q", None)
            stored_query.pop("memberIdentity", None)
            stored_query.pop("variables", None)
            if decoration_id:
                stored_query["decorationId"] = decoration_id
        incoming = OperationSpec(
            name=name,
            method=(request.get("method") or "GET").upper(),
            path=path or IDENTITY_COLLECTION_PATH,
            query=stored_query,
            query_id=query_id,
            decoration_id=decoration_id,
        )
        score = identity_operation_score(incoming) if name == "identity" else 0
        existing = operations.get(name)
        if existing is not None and name == "identity" and score < scores.get(name, 0):
            continue
        operations[name] = incoming
        scores[name] = score
        if name == "identity" and score >= 10:
            identity_headers = sanitize_headers(merged_headers)
    if identity_headers:
        headers.update(identity_headers)
    page_instance = headers.get("x-li-page-instance", "")
    if page_instance and "profile" not in page_instance.lower():
        headers.pop("x-li-page-instance", None)
    captured = CapturedEndpoints(
        version=1,
        imported_at=datetime.now(timezone.utc).isoformat(),
        source_har=har_path.name,
        headers=sanitize_headers(headers),
        operations=operations,
    )
    dump_captured_endpoints(output_path, captured)
    return captured


def _classify_operation(path: str, query: dict[str, str], lowered_url: str) -> str | None:
    decoded_path = unquote(path)
    decoration = query.get("decorationId") or ""
    if "identity/dash/profiles" in decoded_path:
        if "fsd_profile" in decoded_path or "FullProfile" in decoration or query.get("q") == "memberIdentity":
            return "identity"
    query_id = (query.get("queryId") or "").lower()
    blob = f"{decoded_path.lower()} {query_id} {lowered_url}"
    for name, hints in _OPERATION_HINTS:
        if any(hint in blob for hint in hints):
            return name
    return None
