from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.config import Settings, get_settings
from linkedin_profile_api.linkedin.client import LinkedInClient
from linkedin_profile_api.linkedin.query_discovery import QueryDiscovery
from linkedin_profile_api.linkedin.query_registry import QueryRegistry
from linkedin_profile_api.linkedin.session import SessionManager
from linkedin_profile_api.security.api_key import KeyRole, require_api_key
from linkedin_profile_api.security.rate_limit import RateLimiter
from linkedin_profile_api.service import ProfileService


def get_cache(request: Request) -> CacheStore:
    return request.app.state.cache


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def get_client(request: Request) -> LinkedInClient:
    return request.app.state.client


def get_registry(request: Request) -> QueryRegistry:
    return request.app.state.registry


def get_discovery(request: Request) -> QueryDiscovery:
    return request.app.state.discovery


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_profile_service(request: Request) -> ProfileService:
    return request.app.state.profile_service


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[CacheStore, Depends(get_cache)]
SessionDep = Annotated[SessionManager, Depends(get_session_manager)]
ClientDep = Annotated[LinkedInClient, Depends(get_client)]
KeyDep = Annotated[KeyRole, Depends(require_api_key)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
ServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
