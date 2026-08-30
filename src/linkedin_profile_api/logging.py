from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

_SECRET_KEYS = frozenset(
    {
        "cookie",
        "authorization",
        "csrf-token",
        "x-api-key",
        "li_at",
        "jsessionid",
        "api_key",
        "demo_api_key",
        "linkedin_li_at",
        "linkedin_jsessionid",
        "linkedin_cookie_jar",
        "linkedin_cookie_jar_failover",
        "linkedin_egress_proxy",
        "_px3",
        "bcookie",
        "bscookie",
    }
)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")


def log_event(logger: logging.Logger, **fields: Any) -> None:
    safe = {key: value for key, value in fields.items() if key.lower() not in _SECRET_KEYS}
    for key, value in list(safe.items()):
        if isinstance(value, UUID):
            safe[key] = str(value)
    logger.info(json.dumps(safe, default=str))
