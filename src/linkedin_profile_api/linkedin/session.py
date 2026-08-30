from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.config import Settings
from linkedin_profile_api.linkedin.headers import strip_jsessionid_quotes

OUTCOME_OK = "ok"
OUTCOME_EXPIRED = "expired"
OUTCOME_BLOCKED = "blocked"
OUTCOME_RATE_LIMITED = "rate_limited"

COOKIE_DOMAIN = ".linkedin.com"


def parse_cookie_jar(raw: str) -> dict[str, str]:
    text = raw.strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items() if key and value is not None}
    cookies: dict[str, str] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            cookies[name] = value.strip()
    return cookies


def _normalize_jsessionid(cookies: dict[str, str]) -> dict[str, str]:
    if "JSESSIONID" not in cookies:
        for key in list(cookies):
            if key.lower() == "jsessionid":
                cookies["JSESSIONID"] = cookies.pop(key)
                break
    return cookies


@dataclass
class CookiePair:
    slot: str
    cookies: dict[str, str]

    @property
    def li_at(self) -> str:
        return self.cookies.get("li_at", "")

    @property
    def jsessionid(self) -> str:
        return self.cookies.get("JSESSIONID", "")

    @property
    def csrf_token(self) -> str:
        return strip_jsessionid_quotes(self.jsessionid)


class SessionManager:
    def __init__(self, settings: Settings, cache: CacheStore) -> None:
        self._settings = settings
        self._cache = cache
        self._active_slot = "primary"
        self._failed_over = False

    def cookies_loaded(self) -> bool:
        pair = self.active_pair()
        return bool(pair and pair.li_at and pair.jsessionid)

    def active_pair(self) -> CookiePair | None:
        if self._active_slot == "failover":
            return self._failover_pair()
        return self._primary_pair()

    def active_slot(self) -> str:
        return self._active_slot

    def cookie_dict(self) -> dict[str, str]:
        pair = self.active_pair()
        if pair is None:
            return {}
        return dict(pair.cookies)

    def _primary_pair(self) -> CookiePair | None:
        return self._pair_from(
            "primary",
            self._settings.linkedin_cookie_jar,
            self._settings.linkedin_li_at,
            self._settings.linkedin_jsessionid,
        )

    def _failover_pair(self) -> CookiePair | None:
        return self._pair_from(
            "failover",
            self._settings.linkedin_cookie_jar_failover,
            self._settings.linkedin_li_at_failover,
            self._settings.linkedin_jsessionid_failover,
        )

    def _pair_from(self, slot: str, jar_raw: str, li_at: str, jsessionid: str) -> CookiePair | None:
        cookies = _normalize_jsessionid(parse_cookie_jar(jar_raw))
        if li_at:
            cookies["li_at"] = li_at
        if jsessionid:
            cookies["JSESSIONID"] = jsessionid
        if not cookies.get("li_at") or not cookies.get("JSESSIONID"):
            return None
        return CookiePair(slot=slot, cookies=cookies)

    async def mark_ok(self) -> None:
        pair = self.active_pair()
        if pair is None:
            return
        await self._cache.set_session_outcome(pair.slot, OUTCOME_OK)

    async def mark_failure(self, outcome: str) -> bool:
        pair = self.active_pair()
        if pair is not None:
            await self._cache.set_session_outcome(pair.slot, outcome)
        switched = False
        if (
            not self._failed_over
            and self._active_slot == "primary"
            and self._failover_pair() is not None
            and outcome in {OUTCOME_EXPIRED, OUTCOME_BLOCKED}
        ):
            self._active_slot = "failover"
            self._failed_over = True
            switched = True
        return switched

    async def last_outcome(self, slot: str = "primary") -> dict[str, str] | None:
        row = await self._cache.get_session_state(slot)
        if row is None:
            return None
        return {"slot": row["slot"], "last_outcome": row["last_outcome"], "last_outcome_at": row["last_outcome_at"]}

    async def is_session_stale(self) -> bool:
        row = await self.last_outcome(self._active_slot)
        if row is None:
            return False
        if row["last_outcome"] == OUTCOME_OK:
            return False
        age = self._age_seconds(row)
        if age is None:
            return False
        return age <= self._settings.session_stale_after_seconds

    async def should_probe(self) -> bool:
        if not self.cookies_loaded():
            return False
        row = await self.last_outcome(self._active_slot)
        if row is None:
            return True
        age = self._age_seconds(row)
        if age is None:
            return True
        if row["last_outcome"] == OUTCOME_OK:
            return age >= self._settings.session_probe_interval_seconds
        if row["last_outcome"] in {OUTCOME_EXPIRED, OUTCOME_BLOCKED}:
            return age > self._settings.session_stale_after_seconds
        return age >= self._settings.session_probe_interval_seconds

    def _age_seconds(self, row: dict[str, str]) -> float | None:
        raw = row.get("last_outcome_at")
        if not raw:
            return None
        stamped = datetime.fromisoformat(raw)
        return (datetime.now(timezone.utc) - stamped.astimezone(timezone.utc)).total_seconds()
