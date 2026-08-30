from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.config import Settings
from linkedin_profile_api.linkedin.client import LinkedInClient, progress
from linkedin_profile_api.linkedin.session import CookiePair
from linkedin_profile_api.linkedin.exceptions import (
    LinkedInProtocolChangedError,
    SectionFetchError,
    UpstreamDeadlineError,
)
from linkedin_profile_api.linkedin.query_discovery import QueryDiscovery
from linkedin_profile_api.linkedin.query_registry import QueryRegistry
from linkedin_profile_api.linkedin.urn_resolver import resolve_graph
from linkedin_profile_api.linkedin.url import canonical_profile_url, parse_profile_url
from linkedin_profile_api.linkedin.visibility import detect_visibility, section_state_for_visibility
from linkedin_profile_api.logging import log_event
from linkedin_profile_api.parsers.certifications import parse_certifications
from linkedin_profile_api.parsers.education import parse_education
from linkedin_profile_api.parsers.experience import parse_experience
from linkedin_profile_api.parsers.honors import parse_honors
from linkedin_profile_api.parsers.images import parse_images
from linkedin_profile_api.parsers.languages import parse_languages
from linkedin_profile_api.parsers.profile import extract_entity_urn, parse_top_card
from linkedin_profile_api.parsers.projects import parse_projects
from linkedin_profile_api.parsers.publications import parse_publications
from linkedin_profile_api.parsers.skills import parse_skills
from linkedin_profile_api.parsers.volunteering import parse_volunteering
from linkedin_profile_api.schemas.profile import Profile
from linkedin_profile_api.schemas.response import ProfileResponse, SectionName, SectionState, Visibility

logger = logging.getLogger("linkedin_profile_api")

Parser = Callable[[Any, Visibility], tuple[list[Any], SectionState]]

SECTION_PARSERS: dict[SectionName, Parser] = {
    SectionName.EXPERIENCE: parse_experience,
    SectionName.EDUCATION: parse_education,
    SectionName.SKILLS: parse_skills,
    SectionName.CERTIFICATIONS: parse_certifications,
    SectionName.LANGUAGES: parse_languages,
    SectionName.VOLUNTEERING: parse_volunteering,
    SectionName.PROJECTS: parse_projects,
    SectionName.PUBLICATIONS: parse_publications,
    SectionName.HONORS: parse_honors,
}

OPTIONAL_SECTIONS = (
    SectionName.EXPERIENCE,
    SectionName.EDUCATION,
    SectionName.SKILLS,
    SectionName.CERTIFICATIONS,
    SectionName.LANGUAGES,
    SectionName.VOLUNTEERING,
    SectionName.PROJECTS,
    SectionName.PUBLICATIONS,
    SectionName.HONORS,
)


class ProfileService:
    def __init__(
        self,
        settings: Settings,
        cache: CacheStore,
        client: LinkedInClient,
        registry: QueryRegistry,
        discovery: QueryDiscovery,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._client = client
        self._registry = registry
        self._discovery = discovery

    async def fetch(
        self,
        profile_url: str,
        request_id: UUID,
        *,
        bypass_cache: bool = False,
        request_cookies: CookiePair | None = None,
    ) -> ProfileResponse:
        started = datetime.now(timezone.utc)
        deadline = started + timedelta(seconds=self._settings.request_deadline_seconds)
        slug = parse_profile_url(profile_url, max_length=self._settings.max_url_length)
        skip_cache_read = bypass_cache or request_cookies is not None

        cached = None if skip_cache_read else await self._cache.get_profile(slug)
        if cached is not None:
            progress(f"profile cache hit for /in/{slug}/")
            response = ProfileResponse.model_validate(cached)
            response.cached = True
            response.request_id = request_id
            log_event(
                logger,
                request_id=request_id,
                event="profile_fetch",
                cached=True,
                caller_session=False,
                visibility=response.profile.visibility,
                section_states=response.sections,
                deadline_hit=False,
            )
            return response

        if datetime.now(timezone.utc) >= deadline:
            raise UpstreamDeadlineError()

        if request_cookies is not None:
            progress(f"using request-scoped LinkedIn cookies for /in/{slug}/")
        async with self._client.request_session(request_cookies):
            return await self._fetch_live(
                slug=slug,
                request_id=request_id,
                started=started,
                deadline=deadline,
                persist_cache=request_cookies is None,
                caller_session=request_cookies is not None,
            )

    async def _fetch_live(
        self,
        *,
        slug: str,
        request_id: UUID,
        started: datetime,
        deadline: datetime,
        persist_cache: bool,
        caller_session: bool,
    ) -> ProfileResponse:
        cached_identity = await self._cache.get_identity(slug)
        cached_urn = cached_identity.get("entity_urn") if cached_identity else None
        progress(f"profile cache miss for /in/{slug}/ cached_urn={bool(cached_urn)}")
        raw_identity = await self._client.resolve_identity(slug, profile_urn=cached_urn)
        identity = resolve_graph(raw_identity)
        visibility = detect_visibility(identity)
        progress(f"identity parsed visibility={visibility}")
        profile = parse_top_card(identity, slug, visibility)
        entity_urn = extract_entity_urn(identity) or cached_urn
        if entity_urn:
            await self._cache.put_identity(slug, entity_urn, visibility.value)

        sections: dict[str, SectionState] = {}
        warnings: list[str] = []
        deadline_hit = False

        image_items, image_state = parse_images(identity, visibility)
        if image_items and not profile.profile_images:
            profile.profile_images = image_items
        sections[SectionName.IMAGES.value] = image_state
        if profile.about:
            sections[SectionName.ABOUT.value] = SectionState.AVAILABLE
        else:
            sections[SectionName.ABOUT.value] = (
                SectionState.INACCESSIBLE if visibility != Visibility.FULL else SectionState.EMPTY
            )

        for name in OPTIONAL_SECTIONS:
            if datetime.now(timezone.utc) >= deadline:
                deadline_hit = True
                sections[name.value] = SectionState.FAILED
                warnings.append(f"{name.value} skipped after request deadline.")
                continue
            if visibility in {Visibility.OUT_OF_NETWORK, Visibility.LIMITED}:
                sections[name.value] = SectionState.INACCESSIBLE
                continue
            local_items, local_state = SECTION_PARSERS[name](identity, visibility)
            if local_items:
                sections[name.value] = local_state
                _assign_section(profile, name, local_items)
                continue
            items, state = await self._load_section(name, slug, entity_urn, visibility, deadline)
            sections[name.value] = state
            _assign_section(profile, name, items)
            if state == SectionState.FAILED:
                warnings.append(f"{name.value} could not be fetched.")
            elif state == SectionState.UPSTREAM_CHANGED:
                warnings.append(f"{name.value} changed upstream and was not refreshed.")

        fetched_at = datetime.now(timezone.utc)
        response = ProfileResponse(
            request_id=request_id,
            fetched_at=fetched_at,
            cached=False,
            deadline_hit=deadline_hit,
            profile=profile,
            sections=sections,
            warnings=warnings,
        )
        if persist_cache:
            await self._cache.put_profile(slug, response.model_dump(mode="json"), profile.visibility)
        log_event(
            logger,
            request_id=request_id,
            event="profile_fetch",
            cached=False,
            caller_session=caller_session,
            visibility=profile.visibility,
            section_states=sections,
            deadline_hit=deadline_hit,
            duration_ms=int((fetched_at - started).total_seconds() * 1000),
            profile_url=canonical_profile_url(slug),
        )
        return response

    async def _load_section(
        self,
        name: SectionName,
        slug: str,
        entity_urn: str | None,
        visibility: Visibility,
        deadline: datetime,
    ) -> tuple[list[Any], SectionState]:
        parser = SECTION_PARSERS[name]
        spec = await self._registry.resolve(name.value)
        if not spec.query_id:
            return [], section_state_for_visibility(visibility, [])
        try:
            raw = await self._fetch_with_discovery(spec.name, spec, slug, entity_urn, deadline)
        except SectionFetchError:
            return [], SectionState.FAILED
        except LinkedInProtocolChangedError:
            return [], SectionState.UPSTREAM_CHANGED
        except Exception:
            return [], SectionState.FAILED
        graph = resolve_graph(raw)
        return parser(graph, visibility)

    async def _fetch_with_discovery(
        self,
        operation_name: str,
        spec: Any,
        slug: str,
        entity_urn: str | None,
        deadline: datetime,
    ) -> Any:
        try:
            raw = await self._client.fetch_operation(spec, slug=slug, profile_urn=entity_urn)
            await self._registry.remember(
                operation_name,
                spec.query_id,
                spec.decoration_id,
                None,
                mark_success=True,
            )
            return raw
        except (LinkedInProtocolChangedError, SectionFetchError):
            rediscovered = await self._discovery.invalidate_and_rediscover(operation_name, slug, deadline)
            if not rediscovered:
                raise
            refreshed = await self._registry.resolve(operation_name)
            return await self._client.fetch_operation(refreshed, slug=slug, profile_urn=entity_urn)


def _assign_section(profile: Profile, name: SectionName, items: list[Any]) -> None:
    mapping = {
        SectionName.EXPERIENCE: "experience",
        SectionName.EDUCATION: "education",
        SectionName.SKILLS: "skills",
        SectionName.CERTIFICATIONS: "certifications",
        SectionName.LANGUAGES: "languages",
        SectionName.VOLUNTEERING: "volunteering",
        SectionName.PROJECTS: "projects",
        SectionName.PUBLICATIONS: "publications",
        SectionName.HONORS: "honors",
    }
    field_name = mapping.get(name)
    if field_name is not None:
        setattr(profile, field_name, items)
