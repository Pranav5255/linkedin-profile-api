from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse

from linkedin_profile_api.config import Settings
from linkedin_profile_api.linkedin.allowlist import is_allowed_bundle_url
from linkedin_profile_api.linkedin.client import LINKEDIN_ORIGIN, LinkedInClient
from linkedin_profile_api.linkedin.query_registry import QueryRegistry

ASSET_RE = re.compile(
    r"""https://(?:static\.)?licdn\.com/[^"'\\\s>]+\.js""",
    re.IGNORECASE,
)
QUERY_RE = re.compile(
    r"""(?P<name>voyager[A-Za-z0-9]+)\.(?P<hash>[a-f0-9]{32})""",
)
DECORATION_RE = re.compile(
    r"""(com\.linkedin\.voyager[A-Za-z0-9.]+-\d+)""",
)

OPERATION_ALIASES = {
    "experience": ("voyagerIdentityDashProfileComponents", "voyagerIdentityDashProfileCards"),
    "education": ("voyagerIdentityDashProfileComponents", "voyagerIdentityDashProfileCards"),
    "skills": ("voyagerIdentityDashSkillsByProfile", "voyagerIdentityDashProfileComponents"),
    "certifications": ("voyagerIdentityDashProfileComponents",),
    "languages": ("voyagerIdentityDashProfileComponents",),
    "about": ("voyagerIdentityDashProfileComponents",),
    "volunteering": ("voyagerIdentityDashProfileComponents",),
    "projects": ("voyagerIdentityDashProfileComponents",),
    "publications": ("voyagerIdentityDashProfileComponents",),
    "honors": ("voyagerIdentityDashProfileComponents",),
}


class QueryDiscovery:
    def __init__(
        self,
        settings: Settings,
        client: LinkedInClient,
        registry: QueryRegistry,
    ) -> None:
        self._settings = settings
        self._client = client
        self._registry = registry
        self._rediscovered: set[str] = set()

    def remaining_budget(self, deadline: datetime) -> float:
        return (deadline - datetime.now(timezone.utc)).total_seconds()

    async def discover_for(
        self,
        operation_name: str,
        slug: str,
        deadline: datetime,
    ) -> bool:
        if operation_name in self._rediscovered:
            return False
        if self.remaining_budget(deadline) < 8:
            return False
        html = await self._client.get_text(
            f"{LINKEDIN_ORIGIN}/in/{slug}/",
            timeout=self._settings.bundle_fetch_timeout_seconds,
            max_bytes=self._settings.bundle_max_bytes,
        )
        assets = self._select_assets(html)
        found = False
        for asset in assets:
            if self.remaining_budget(deadline) < 6:
                break
            body = await self._client.get_text(
                asset,
                timeout=self._settings.bundle_fetch_timeout_seconds,
                max_bytes=self._settings.bundle_max_bytes,
            )
            for name, query_id in self._extract_query_ids(body):
                if self._matches(operation_name, name):
                    await self._registry.remember(operation_name, query_id, None, asset)
                    found = True
            for decoration in DECORATION_RE.findall(body):
                if "profile" in decoration.lower() and operation_name == "identity":
                    await self._registry.remember(operation_name, None, decoration, asset)
                    found = True
        self._rediscovered.add(operation_name)
        return found

    async def invalidate_and_rediscover(
        self,
        operation_name: str,
        slug: str,
        deadline: datetime,
    ) -> bool:
        if operation_name in self._rediscovered:
            return False
        await self._registry.invalidate(operation_name)
        return await self.discover_for(operation_name, slug, deadline)

    def _select_assets(self, html: str) -> list[str]:
        seen: list[str] = []
        for match in ASSET_RE.findall(html):
            url = match
            if url.startswith("//"):
                url = f"https:{url}"
            elif url.startswith("/"):
                url = urljoin(LINKEDIN_ORIGIN, url)
            parsed = urlparse(url)
            if parsed.netloc and parsed.scheme != "https":
                continue
            if not is_allowed_bundle_url(url):
                continue
            if url not in seen:
                seen.append(url)
            if len(seen) >= self._settings.bundle_max_assets:
                break
        return seen

    def _extract_query_ids(self, body: str) -> Iterable[tuple[str, str]]:
        for match in QUERY_RE.finditer(body):
            yield match.group("name"), f"{match.group('name')}.{match.group('hash')}"

    def _matches(self, operation_name: str, query_name: str) -> bool:
        aliases = OPERATION_ALIASES.get(operation_name, (operation_name,))
        return any(alias.lower() in query_name.lower() for alias in aliases)
