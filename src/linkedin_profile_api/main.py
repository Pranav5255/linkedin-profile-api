from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from linkedin_profile_api.api.errors import install_exception_handlers
from linkedin_profile_api.api.json_response import PrettyJSONResponse
from linkedin_profile_api.api.routes import router
from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.config import get_settings
from linkedin_profile_api.linkedin.client import LinkedInClient
from linkedin_profile_api.linkedin.endpoints import load_captured_endpoints
from linkedin_profile_api.linkedin.query_discovery import QueryDiscovery
from linkedin_profile_api.linkedin.query_registry import QueryRegistry
from linkedin_profile_api.linkedin.session import SessionManager
from linkedin_profile_api.logging import configure_logging
from linkedin_profile_api.security.rate_limit import RateLimiter
from linkedin_profile_api.service import ProfileService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    cache = CacheStore(settings.cache_database_path, settings.cache_ttl_seconds)
    await cache.open()
    captured = load_captured_endpoints(settings.captured_endpoints_path)
    sessions = SessionManager(settings, cache)
    client = LinkedInClient(settings, sessions, captured)
    await client.start()
    registry = QueryRegistry(cache, captured)
    await registry.seed_from_captured()
    discovery = QueryDiscovery(settings, client, registry)
    limiter = RateLimiter(settings.evaluator_quota_per_hour, settings.demo_quota_per_hour)
    service = ProfileService(settings, cache, client, registry, discovery)
    app.state.settings = settings
    app.state.cache = cache
    app.state.session_manager = sessions
    app.state.client = client
    app.state.registry = registry
    app.state.discovery = discovery
    app.state.rate_limiter = limiter
    app.state.profile_service = service
    try:
        yield
    finally:
        await client.close()
        await cache.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LinkedIn Profile API",
        version="0.1.0",
        description="Resolve a LinkedIn profile URL to structured JSON via reverse-engineered Voyager HTTP endpoints.",
        default_response_class=PrettyJSONResponse,
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(router)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        if request.method == "POST":
            body = await request.body()
            settings = get_settings()
            if len(body) > settings.max_request_body_bytes:
                return PrettyJSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "invalid_profile_url",
                            "message": "Request body is too large.",
                            "request_id": str(request.state.request_id),
                        }
                    },
                )
        return await call_next(request)

    return app


app = create_app()
