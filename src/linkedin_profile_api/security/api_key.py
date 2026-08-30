from __future__ import annotations

import hmac
from enum import StrEnum

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from linkedin_profile_api.config import Settings, get_settings
from linkedin_profile_api.linkedin.exceptions import InvalidApiKeyError

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class KeyRole(StrEnum):
    EVALUATOR = "evaluator"
    DEMO = "demo"


def classify_api_key(provided: str | None, settings: Settings) -> KeyRole:
    if not provided:
        raise InvalidApiKeyError()
    if settings.api_key and hmac.compare_digest(provided, settings.api_key):
        return KeyRole.EVALUATOR
    if settings.demo_api_key and hmac.compare_digest(provided, settings.demo_api_key):
        return KeyRole.DEMO
    raise InvalidApiKeyError()


async def require_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
    settings: Settings = Depends(get_settings),
) -> KeyRole:
    return classify_api_key(api_key, settings)
