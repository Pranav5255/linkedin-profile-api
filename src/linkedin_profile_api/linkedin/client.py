from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from curl_cffi.requests import AsyncSession, RequestsError, Response

from linkedin_profile_api.config import Settings
from linkedin_profile_api.linkedin.endpoints import (
    TOP_CARD_DECORATION,
    CapturedEndpoints,
    OperationSpec,
    identity_decoration_candidates,
)
from linkedin_profile_api.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInProtocolChangedError,
    LinkedInRateLimitedError,
    LinkedInSessionExpiredError,
    ProfileNotFoundError,
    SectionFetchError,
    UpstreamTimeoutError,
)
from linkedin_profile_api.linkedin.headers import build_request_headers
from linkedin_profile_api.linkedin.profile_urn import (
    extract_profile_urn_from_html,
    extract_profile_urn_from_payload,
    identity_profile_path,
    normalize_profile_urn,
)
from linkedin_profile_api.linkedin.urn_resolver import identity_payload_has_sections
from linkedin_profile_api.linkedin.session import (
    COOKIE_DOMAIN,
    OUTCOME_BLOCKED,
    OUTCOME_EXPIRED,
    OUTCOME_OK,
    OUTCOME_RATE_LIMITED,
    SessionManager,
)

LINKEDIN_ORIGIN = "https://www.linkedin.com"
NEVER_RETRY_STATUSES = frozenset({401, 403, 429, 999})
XSSI_PREFIXES = (")]}',\n", ")]}',", ")]}'", "for(;;);", "while(1);")
AUTH_REDIRECT_MARKERS = ("authwall", "checkpoint", "/login", "uas/", "signup", "challenge")
DOCUMENT_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
)
PROFILE_HTML_MAX_BYTES = 5_000_000
_PROGRESS_ENABLED = True


def set_progress(enabled: bool) -> None:
    global _PROGRESS_ENABLED
    _PROGRESS_ENABLED = enabled


def progress(message: str) -> None:
    if not _PROGRESS_ENABLED:
        return
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


def _redirect_target(location: str) -> str:
    if location.startswith("https://") or location.startswith("http://"):
        return location
    return urljoin(LINKEDIN_ORIGIN, location)


def _redirect_kind(location: str) -> str:
    lowered = location.lower()
    if any(marker in lowered for marker in AUTH_REDIRECT_MARKERS):
        return "auth"
    parsed = urlparse(_redirect_target(location))
    host = (parsed.hostname or "").lower()
    if host in {"www.linkedin.com", "linkedin.com"} and parsed.path.startswith("/voyager/"):
        return "voyager"
    return "other"


def _same_resource(left: str, right: str) -> bool:
    if not left or not right:
        return False
    source = urlparse(_redirect_target(left))
    dest = urlparse(_redirect_target(right))
    return (source.hostname or "").lower() == (dest.hostname or "").lower() and source.path.rstrip(
        "/"
    ) == dest.path.rstrip("/")


def _is_redirect_loop(exc: RequestsError) -> bool:
    text = str(exc).lower()
    return "redirect" in text or "curl: (47)" in text


class LinkedInClient:
    def __init__(
        self,
        settings: Settings,
        session_manager: SessionManager,
        captured: CapturedEndpoints,
    ) -> None:
        self._settings = settings
        self._sessions = session_manager
        self._captured = captured
        self._http: AsyncSession | None = None
        self._semaphore = asyncio.Semaphore(max(1, settings.max_upstream_concurrency))
        self._last_call_at: float | None = None
        self._bound_slot: str | None = None

    async def start(self) -> None:
        kwargs: dict[str, Any] = {
            "impersonate": self._settings.linkedin_impersonate or "chrome124",
            "allow_redirects": False,
        }
        if self._settings.linkedin_egress_proxy:
            kwargs["proxy"] = self._settings.linkedin_egress_proxy
        self._http = AsyncSession(**kwargs)
        self._apply_cookies()

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()
            self._http = None
            self._bound_slot = None

    def reload_captured(self, captured: CapturedEndpoints) -> None:
        self._captured = captured

    async def get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
    ) -> Any:
        response = await self._request("GET", path, params=params, referer=referer)
        return self._parse_json(response, path=path)

    async def get_text(
        self,
        url: str,
        *,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> str:
        await self._pace()
        self._sync_cookies()
        http = self._require()
        try:
            async with self._semaphore:
                response = await http.get(
                    url,
                    headers=self._headers(),
                    timeout=timeout or self._settings.upstream_timeout_seconds,
                    allow_redirects=False,
                )
        except RequestsError as exc:
            if _is_redirect_loop(exc):
                raise LinkedInSessionExpiredError() from exc
            raise UpstreamTimeoutError() from exc
        if response.status_code in {401, 403, 999, 429}:
            await self._classify_status(response)
        raw = response.content or b""
        if max_bytes is not None and len(raw) > max_bytes:
            raw = raw[:max_bytes]
        return raw.decode("utf-8", errors="replace")

    async def get_html(
        self,
        url: str,
        *,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> str:
        progress(f"GET HTML {url}")
        await self._pace()
        self._sync_cookies()
        http = self._require()
        try:
            async with self._semaphore:
                response = await http.get(
                    url,
                    headers=self._document_headers(),
                    timeout=timeout or self._settings.upstream_timeout_seconds,
                    allow_redirects=False,
                )
        except RequestsError as exc:
            if _is_redirect_loop(exc):
                raise LinkedInSessionExpiredError() from exc
            raise UpstreamTimeoutError() from exc
        await self._classify_document(response)
        raw = response.content or b""
        if max_bytes is not None and len(raw) > max_bytes:
            raw = raw[:max_bytes]
        progress(f"HTML {response.status_code} {len(raw)} bytes")
        return raw.decode("utf-8", errors="replace")

    async def resolve_identity(self, slug: str, profile_urn: str | None = None) -> Any:
        urn = await self.resolve_profile_urn(slug, cached_urn=profile_urn)
        spec = self._captured.operation("identity")
        captured_decoration = None
        if spec is not None:
            captured_decoration = spec.decoration_id or spec.query.get("decorationId")
        referer = f"{LINKEDIN_ORIGIN}/in/{slug}/"
        last_protocol_error: LinkedInProtocolChangedError | None = None
        last_shallow: Any = None
        path = identity_profile_path(urn)
        candidates = identity_decoration_candidates(captured_decoration)
        for index, decoration in enumerate(candidates):
            progress(f"GET {path} decoration={decoration.rsplit('.', 1)[-1]}")
            try:
                payload = await self.get_json(path, params={"decorationId": decoration}, referer=referer)
            except LinkedInProtocolChangedError as exc:
                progress(f"identity decoration {decoration.rsplit('.', 1)[-1]} rejected: {exc}")
                last_protocol_error = exc
                continue
            if identity_payload_has_sections(payload) or index == len(candidates) - 1:
                progress(f"identity decoration {decoration.rsplit('.', 1)[-1]} succeeded")
                return payload
            last_shallow = payload
            progress(
                f"identity decoration {decoration.rsplit('.', 1)[-1]} was top-card only; trying a richer decoration"
            )
        if last_shallow is not None:
            progress("no richer decoration returned sections; using last top-card payload")
            return last_shallow
        if last_protocol_error is not None:
            raise last_protocol_error
        raise LinkedInProtocolChangedError("LinkedIn identity decorations were rejected.")

    async def resolve_profile_urn(self, slug: str, cached_urn: str | None = None) -> str:
        cached = normalize_profile_urn(cached_urn)
        if cached:
            progress(f"URN cache hit for /in/{slug}/")
            return cached
        progress(f"resolving URN for /in/{slug}/ from profile HTML")
        try:
            html = await self.get_html(
                f"{LINKEDIN_ORIGIN}/in/{slug}/",
                max_bytes=PROFILE_HTML_MAX_BYTES,
            )
            from_html = extract_profile_urn_from_html(html, slug)
            if from_html:
                progress(f"URN extracted from profile HTML: {from_html}")
                return from_html
            progress("profile HTML had no matching URN")
        except (UpstreamTimeoutError, LinkedInProtocolChangedError) as exc:
            progress(f"profile HTML failed: {exc}")
        progress("trying memberIdentity fallback for URN")
        from_lookup = await self._lookup_urn_via_member_identity(slug)
        if from_lookup:
            progress("URN resolved via memberIdentity fallback")
            return from_lookup
        raise LinkedInProtocolChangedError(
            f"Could not resolve a profile URN for /in/{slug}/ from the LinkedIn profile page."
        )

    async def ping_me(self) -> Any:
        return await self.get_json("/voyager/api/me", referer=f"{LINKEDIN_ORIGIN}/feed/")

    async def decoy_feed(self) -> None:
        try:
            await self.get_json("/voyager/api/feed/updatesV2", referer=f"{LINKEDIN_ORIGIN}/feed/")
        except (
            LinkedInProtocolChangedError,
            LinkedInSessionExpiredError,
            ProfileNotFoundError,
            UpstreamTimeoutError,
        ):
            return

    async def probe_if_due(self) -> None:
        if not await self._sessions.should_probe():
            return
        try:
            await self.ping_me()
        except (LinkedInProtocolChangedError, ProfileNotFoundError, UpstreamTimeoutError):
            return

    async def warmup_session(self) -> None:
        try:
            await self.ping_me()
        except (LinkedInProtocolChangedError, ProfileNotFoundError, UpstreamTimeoutError):
            pass
        if self._settings.linkedin_decoy_feed:
            await self.decoy_feed()

    async def fetch_operation(
        self,
        spec: OperationSpec,
        *,
        slug: str,
        profile_urn: str | None,
    ) -> Any:
        referer = f"{LINKEDIN_ORIGIN}/in/{slug}/"
        try:
            if spec.name == "identity":
                return await self.resolve_identity(slug, profile_urn=profile_urn)
            params = dict(spec.query)
            if spec.query_id:
                params["queryId"] = spec.query_id
            if spec.decoration_id and "decorationId" not in params:
                params["decorationId"] = spec.decoration_id
            if "memberIdentity" in params:
                params["memberIdentity"] = slug
            if profile_urn and "variables" not in params and spec.path.endswith("/graphql"):
                encoded_urn = profile_urn.replace(":", "%3A")
                params.setdefault("variables", f"(profileUrn:{encoded_urn})")
            return await self.get_json(spec.path or "/voyager/api/graphql", params=params, referer=referer)
        except (LinkedInProtocolChangedError, ProfileNotFoundError) as exc:
            raise SectionFetchError(str(exc)) from exc

    async def _lookup_urn_via_member_identity(self, slug: str) -> str | None:
        try:
            payload = await self.get_json(
                "/voyager/api/identity/dash/profiles",
                params={
                    "q": "memberIdentity",
                    "memberIdentity": slug,
                    "decorationId": TOP_CARD_DECORATION,
                },
                referer=f"{LINKEDIN_ORIGIN}/in/{slug}/",
            )
        except (
            LinkedInProtocolChangedError,
            LinkedInSessionExpiredError,
            ProfileNotFoundError,
            UpstreamTimeoutError,
        ):
            return None
        return extract_profile_urn_from_payload(payload, slug)

    def _require(self) -> AsyncSession:
        if self._http is None:
            raise RuntimeError("LinkedIn HTTP session is not started.")
        return self._http

    def _apply_cookies(self) -> None:
        http = self._require()
        http.cookies.clear()
        for name, value in self._sessions.cookie_dict().items():
            http.cookies.set(name, value, domain=COOKIE_DOMAIN, path="/", secure=True)
        pair = self._sessions.active_pair()
        self._bound_slot = pair.slot if pair else None

    def _sync_cookies(self) -> None:
        if self._bound_slot != self._sessions.active_slot():
            self._apply_cookies()

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        pair = self._sessions.active_pair()
        csrf = pair.csrf_token if pair else ""
        headers = build_request_headers(csrf, self._captured)
        if referer:
            headers["referer"] = referer
        return headers

    def _document_headers(self) -> dict[str, str]:
        return {
            "accept": DOCUMENT_ACCEPT,
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
        }

    async def _pace(self) -> None:
        delay = random.uniform(
            self._settings.upstream_delay_ms_min / 1000,
            self._settings.upstream_delay_ms_max / 1000,
        )
        await asyncio.sleep(delay)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        referer: str | None = None,
        *,
        retried: bool = False,
        redirect_hops: int = 0,
    ) -> Response:
        if redirect_hops == 0 and not retried:
            await self._pace()
        self._sync_cookies()
        http = self._require()
        url = path if path.startswith("https://") else urljoin(LINKEDIN_ORIGIN, path)
        if params:
            url = f"{url}?{urlencode(params)}"
        try:
            async with self._semaphore:
                response = await http.request(
                    method,
                    url,
                    headers=self._headers(referer),
                    timeout=self._settings.upstream_timeout_seconds,
                    allow_redirects=False,
                )
        except RequestsError as exc:
            if _is_redirect_loop(exc):
                raise LinkedInSessionExpiredError() from exc
            if not retried:
                return await self._request(
                    method, path, params=params, referer=referer, retried=True, redirect_hops=redirect_hops
                )
            raise UpstreamTimeoutError() from exc
        await self._classify_status(response)
        progress(f"{method} {path} -> HTTP {response.status_code}")
        return response

    async def _classify_status(self, response: Response) -> None:
        status = response.status_code
        content_type = (response.headers.get("content-type") or "").lower()
        body = response.text or ""
        html_expected_json = "html" in content_type or body.lstrip().startswith("<")

        if status == 999:
            await self._sessions.mark_failure(OUTCOME_BLOCKED)
            raise LinkedInBlockedError()
        if 300 <= status < 400:
            location = response.headers.get("location") or ""
            current = str(getattr(response, "url", "") or "")
            if location and _same_resource(current, location):
                switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
                if switched:
                    self._sync_cookies()
                    raise LinkedInSessionExpiredError(
                        "Primary session bounced (HTTP 302 to the same URL); failover is now active."
                    )
                raise LinkedInSessionExpiredError()
            if _redirect_kind(location) == "voyager":
                raise LinkedInProtocolChangedError(
                    f"LinkedIn redirected (HTTP {status}) to {location or 'an empty location'}."
                )
            switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
            if switched:
                self._sync_cookies()
                raise LinkedInSessionExpiredError(
                    f"Primary session redirected (HTTP {status}); failover is now active."
                )
            raise LinkedInSessionExpiredError(
                f"LinkedIn redirected the session (HTTP {status}) to {location or 'an empty location'}."
            )
        if status in {401, 403} or html_expected_json:
            switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
            if switched:
                self._sync_cookies()
                raise LinkedInSessionExpiredError("Primary session failed; failover is now active.")
            raise LinkedInSessionExpiredError()
        if status == 429:
            await self._sessions.mark_failure(OUTCOME_RATE_LIMITED)
            raise LinkedInRateLimitedError()
        if status == 404:
            raise ProfileNotFoundError()
        if status >= 400:
            raise LinkedInProtocolChangedError(f"LinkedIn returned HTTP {status}.")
        await self._sessions.mark_ok()

    async def _classify_document(self, response: Response) -> None:
        status = response.status_code
        final_url = str(getattr(response, "url", "") or "")
        location = response.headers.get("location") or final_url
        if status == 999:
            await self._sessions.mark_failure(OUTCOME_BLOCKED)
            raise LinkedInBlockedError()
        if _redirect_kind(location) == "auth" or _redirect_kind(final_url) == "auth":
            switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
            if switched:
                self._sync_cookies()
                raise LinkedInSessionExpiredError(
                    f"Primary session redirected (HTTP {status}); failover is now active."
                )
            raise LinkedInSessionExpiredError(
                f"LinkedIn redirected the session (HTTP {status}) to {location or 'an empty location'}."
            )
        if 300 <= status < 400:
            if location and _same_resource(final_url, location):
                switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
                if switched:
                    self._sync_cookies()
                    raise LinkedInSessionExpiredError(
                        "Primary session bounced (HTTP 302 to the same URL); failover is now active."
                    )
                raise LinkedInSessionExpiredError()
            switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
            if switched:
                self._sync_cookies()
                raise LinkedInSessionExpiredError(
                    f"Primary session redirected (HTTP {status}); failover is now active."
                )
            raise LinkedInSessionExpiredError(
                f"LinkedIn redirected the session (HTTP {status}) to {location or 'an empty location'}."
            )
        if status in {401, 403}:
            switched = await self._sessions.mark_failure(OUTCOME_EXPIRED)
            if switched:
                self._sync_cookies()
                raise LinkedInSessionExpiredError("Primary session failed; failover is now active.")
            raise LinkedInSessionExpiredError()
        if status == 429:
            await self._sessions.mark_failure(OUTCOME_RATE_LIMITED)
            raise LinkedInRateLimitedError()
        if status == 404:
            raise ProfileNotFoundError()
        if status >= 400:
            raise LinkedInProtocolChangedError(f"LinkedIn returned HTTP {status} for a profile page.")
        await self._sessions.mark_ok()

    def _parse_json(self, response: Response, *, path: str = "") -> Any:
        text = self._strip_xssi(response.text or "")
        if text.startswith("<"):
            raise LinkedInSessionExpiredError()
        if not text:
            raise LinkedInProtocolChangedError(
                f"LinkedIn returned an empty body (HTTP {response.status_code}) for {path or 'request'}."
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            preview = text[:80].replace("\n", " ")
            raise LinkedInProtocolChangedError(
                f"LinkedIn returned a non-JSON body (HTTP {response.status_code}) for {path or 'request'}: {preview}"
            ) from exc

    def _strip_xssi(self, raw: str) -> str:
        text = raw.lstrip()
        for prefix in XSSI_PREFIXES:
            if text.startswith(prefix):
                return text[len(prefix) :].lstrip()
        return text
