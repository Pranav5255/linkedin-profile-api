from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from linkedin_profile_api.linkedin.profile_urn import (
    IDENTITY_COLLECTION_PATH,
    normalize_identity_collection_path,
)

STRIPPED_HEADER_NAMES = frozenset(
    {
        "cookie",
        "set-cookie",
        "authorization",
        "csrf-token",
        "x-csrf-token",
        "li_at",
        "jsessionid",
    }
)

SAFE_CAPTURE_HEADERS = (
    "x-li-lang",
    "x-li-track",
    "x-li-page-instance",
    "referer",
    "x-li-deco-include-micro-schema",
)


@dataclass
class OperationSpec:
    name: str
    method: str = "GET"
    path: str = ""
    query: dict[str, str] = field(default_factory=dict)
    query_id: str | None = None
    decoration_id: str | None = None


@dataclass
class CapturedEndpoints:
    version: int = 1
    imported_at: str | None = None
    source_har: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    operations: dict[str, OperationSpec] = field(default_factory=dict)

    def operation(self, name: str) -> OperationSpec | None:
        return self.operations.get(name)


FULL_PROFILE_DECORATION = "com.linkedin.voyager.dash.deco.identity.profile.FullProfile-76"
FULL_PROFILE_WITH_ENTITIES_DECORATION = (
    "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-93"
)
TOP_CARD_DECORATION = "com.linkedin.voyager.dash.deco.identity.profile.WebTopCardCore-16"
DEFAULT_IDENTITY_DECORATION = FULL_PROFILE_WITH_ENTITIES_DECORATION


def identity_decoration_candidates(captured: str | None = None) -> list[str]:
    candidates: list[str] = []
    if captured and captured not in candidates:
        candidates.append(captured)
    for decoration in (
        FULL_PROFILE_WITH_ENTITIES_DECORATION,
        FULL_PROFILE_DECORATION,
        TOP_CARD_DECORATION,
    ):
        if decoration not in candidates:
            candidates.append(decoration)
    return candidates


def identity_operation_score(spec: OperationSpec) -> int:
    decoration = spec.decoration_id or spec.query.get("decorationId") or ""
    score = 0
    if "FullProfileWithEntities" in decoration:
        score += 14
    elif "FullProfile-76" in decoration:
        score += 8
    elif "FullProfile" in decoration:
        score += 6
    if spec.query_id:
        score -= 4
    if spec.query.get("q") == "memberIdentity":
        score -= 2
    path = spec.path or ""
    if path.rstrip("/").endswith("/profiles") or "identity/dash/profiles" in path:
        score += 4
    return score


_FALLBACK = CapturedEndpoints(
    operations={
        "identity": OperationSpec(
            name="identity",
            method="GET",
            path=IDENTITY_COLLECTION_PATH,
            query={"decorationId": DEFAULT_IDENTITY_DECORATION},
            decoration_id=DEFAULT_IDENTITY_DECORATION,
        )
    }
)


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in STRIPPED_HEADER_NAMES:
            continue
        if lowered not in SAFE_CAPTURE_HEADERS:
            continue
        if value:
            cleaned[lowered] = value
    return cleaned


def load_captured_endpoints(path: Path) -> CapturedEndpoints:
    if not path.exists():
        return CapturedEndpoints(operations=dict(_FALLBACK.operations))
    raw = json.loads(path.read_text(encoding="utf-8"))
    operations: dict[str, OperationSpec] = {}
    for name, spec in raw.get("operations", {}).items():
        path = spec.get("path", "")
        if name == "identity":
            path = normalize_identity_collection_path(path)
        operations[name] = OperationSpec(
            name=name,
            method=spec.get("method", "GET"),
            path=path,
            query=dict(spec.get("query") or {}),
            query_id=spec.get("query_id"),
            decoration_id=spec.get("decoration_id"),
        )
    if "identity" not in operations:
        operations["identity"] = _FALLBACK.operations["identity"]
    return CapturedEndpoints(
        version=int(raw.get("version", 1)),
        imported_at=raw.get("imported_at"),
        source_har=raw.get("source_har"),
        headers=sanitize_headers(raw.get("headers") or {}),
        operations=operations,
    )


def dump_captured_endpoints(path: Path, captured: CapturedEndpoints) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": captured.version,
        "imported_at": captured.imported_at or datetime.now(timezone.utc).isoformat(),
        "source_har": captured.source_har,
        "headers": sanitize_headers(captured.headers),
        "operations": {
            name: {
                "method": spec.method,
                "path": spec.path,
                "query": spec.query,
                "query_id": spec.query_id,
                "decoration_id": spec.decoration_id,
            }
            for name, spec in captured.operations.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
