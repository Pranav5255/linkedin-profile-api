from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, Request

from linkedin_profile_api.dependencies import (
    CacheDep,
    ClientDep,
    KeyDep,
    LimiterDep,
    ServiceDep,
    SessionDep,
    SettingsDep,
)
from linkedin_profile_api.linkedin.exceptions import (
    AppError,
    InvalidLinkedInCookieError,
    InvalidProfileUrlError,
)
from linkedin_profile_api.linkedin.session import CookiePair, pair_from_raw
from linkedin_profile_api.linkedin.url import parse_profile_url
from linkedin_profile_api.schemas.request import ProfileRequest
from linkedin_profile_api.schemas.response import HealthResponse, ProfileResponse, ReadyResponse

router = APIRouter()

LinkedInCookieHeader = Annotated[
    str | None,
    Header(
        alias="X-LinkedIn-Cookie",
        description=(
            "Optional full LinkedIn Cookie header for this request only. "
            "Must include li_at and JSESSIONID. Not stored or logged."
        ),
    ),
]


def resolve_request_cookies(header: str | None, body: str | None) -> CookiePair | None:
    raw = (header or "").strip() or (body or "").strip()
    if not raw:
        return None
    pair = pair_from_raw(raw, slot="request")
    if pair is None:
        raise InvalidLinkedInCookieError()
    return pair


@router.get("/healthz", response_model=HealthResponse, tags=["support"])
async def healthz() -> HealthResponse:
    return HealthResponse()


@router.get("/readyz", response_model=ReadyResponse, tags=["support"])
async def readyz(cache: CacheDep, sessions: SessionDep, client: ClientDep) -> ReadyResponse:
    cache_ok = await cache.ready()
    cookies_loaded = sessions.cookies_loaded()
    if cache_ok and cookies_loaded:
        try:
            await client.probe_if_due()
        except AppError:
            pass
    stale = await sessions.is_session_stale()
    last = await sessions.last_outcome(sessions.active_slot())
    ready = cache_ok and cookies_loaded and not stale
    return ReadyResponse(
        ready=ready,
        cache=cache_ok,
        cookies_loaded=cookies_loaded,
        session_outcome=None if last is None else last.get("last_outcome"),
    )


@router.post("/v1/profiles", response_model=ProfileResponse, tags=["profile"])
async def create_profile(
    payload: ProfileRequest,
    request: Request,
    role: KeyDep,
    limiter: LimiterDep,
    service: ServiceDep,
    settings: SettingsDep,
    x_linkedin_cookie: LinkedInCookieHeader = None,
) -> ProfileResponse:
    limiter.check(role)
    if len(payload.profile_url) > settings.max_url_length:
        raise InvalidProfileUrlError("Profile URL is empty or too long.")
    parse_profile_url(payload.profile_url, max_length=settings.max_url_length)
    request.state.request_id = getattr(request.state, "request_id", uuid4())
    return await service.fetch(
        payload.profile_url,
        request.state.request_id,
        request_cookies=resolve_request_cookies(x_linkedin_cookie, payload.linkedin_cookie),
    )


@router.get("/v1/profiles", response_model=ProfileResponse, tags=["profile"])
async def get_profile(
    url: str,
    request: Request,
    role: KeyDep,
    limiter: LimiterDep,
    service: ServiceDep,
    settings: SettingsDep,
    x_linkedin_cookie: LinkedInCookieHeader = None,
) -> ProfileResponse:
    limiter.check(role)
    if not url or len(url) > settings.max_url_length:
        raise InvalidProfileUrlError("Profile URL is empty or too long.")
    parse_profile_url(url, max_length=settings.max_url_length)
    request.state.request_id = getattr(request.state, "request_id", uuid4())
    return await service.fetch(
        url,
        request.state.request_id,
        request_cookies=resolve_request_cookies(x_linkedin_cookie, None),
    )
