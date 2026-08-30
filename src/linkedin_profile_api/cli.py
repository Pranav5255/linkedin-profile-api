from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import uvicorn

from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.capture.har import import_har
from linkedin_profile_api.config import get_settings
from linkedin_profile_api.linkedin.client import LinkedInClient, progress, set_progress
from linkedin_profile_api.linkedin.exceptions import AppError
from linkedin_profile_api.linkedin.endpoints import load_captured_endpoints
from linkedin_profile_api.linkedin.query_discovery import QueryDiscovery
from linkedin_profile_api.linkedin.query_registry import QueryRegistry
from linkedin_profile_api.linkedin.session import SessionManager
from linkedin_profile_api.linkedin.url import parse_profile_url
from linkedin_profile_api.service import ProfileService


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="linkedin-profile-api")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the HTTPS-facing API process.")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    capture = sub.add_parser("capture", help="Capture tooling.")
    capture_sub = capture.add_subparsers(dest="capture_command", required=True)
    imp = capture_sub.add_parser("import", help="Import a DevTools HAR export.")
    imp.add_argument("har_file", type=Path)
    imp.add_argument("--output", type=Path, default=None)

    spike = sub.add_parser("spike", help="Local go/no-go against a profile URL.")
    spike.add_argument("--url", required=True)

    soak = sub.add_parser("soak", help="Bypass cache and loop fetches until the session dies.")
    soak.add_argument("--url", action="append", dest="urls", required=True, help="Repeatable profile URL.")
    soak.add_argument("--max", type=int, default=60, help="Stop after this many live fetches.")
    soak.add_argument("--pause", type=float, default=8.0, help="Extra seconds between fetches.")
    soak.add_argument("--log", type=Path, default=Path("data/soak.log"))

    args = parser.parse_args(argv)
    if args.command == "serve":
        settings = get_settings()
        timeout = int(settings.request_deadline_seconds) + 15
        uvicorn.run(
            "linkedin_profile_api.main:app",
            host=args.host,
            port=args.port,
            timeout_keep_alive=timeout,
            log_level=settings.log_level.lower(),
        )
        return
    if args.command == "capture" and args.capture_command == "import":
        settings = get_settings()
        output = args.output or settings.captured_endpoints_path
        captured = import_har(args.har_file, output)
        print(f"Wrote {output} with {len(captured.operations)} operations.")
        return
    if args.command == "spike":
        asyncio.run(_run_spike(args.url))
        return
    if args.command == "soak":
        asyncio.run(_run_soak(args.urls, args.max, args.pause, args.log))
        return
    parser.error("Unknown command.")


async def _run_spike(url: str) -> None:
    settings = get_settings()
    slug = parse_profile_url(url, max_length=settings.max_url_length)
    progress(f"spike start slug={slug} timeout={settings.upstream_timeout_seconds}s deadline={settings.request_deadline_seconds}s")
    cache = CacheStore(settings.cache_database_path, settings.cache_ttl_seconds)
    await cache.open()
    captured = load_captured_endpoints(settings.captured_endpoints_path)
    identity = captured.operation("identity")
    progress(
        f"captured operations={list(captured.operations)} "
        f"identity_decoration={(identity.decoration_id if identity else None)}"
    )
    sessions = SessionManager(settings, cache)
    if not sessions.cookies_loaded():
        print(
            "Set LINKEDIN_COOKIE_JAR (full Cookie header) or LINKEDIN_LI_AT and LINKEDIN_JSESSIONID.",
            file=sys.stderr,
        )
        await cache.close()
        raise SystemExit(2)
    progress(f"session cookies loaded slot={sessions.active_slot()}")
    client = LinkedInClient(settings, sessions, captured)
    await client.start()
    progress("HTTP session started")
    registry = QueryRegistry(cache, captured)
    await registry.seed_from_captured()
    discovery = QueryDiscovery(settings, client, registry)
    service = ProfileService(settings, cache, client, registry, discovery)
    try:
        progress("fetch begin")
        response = await service.fetch(url, uuid4())
        print(json.dumps(response.model_dump(mode="json"), indent=2))
        progress(
            f"done visibility={response.profile.visibility} cached={response.cached} "
            f"deadline_hit={response.deadline_hit} sections={response.sections}"
        )
    except AppError as exc:
        progress(f"failed {exc.code}: {exc.message}")
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        await client.close()
        await cache.close()
        progress("session closed")


_FATAL_SOAK = frozenset({"linkedin_session_expired", "linkedin_blocked"})


async def _run_soak(urls: list[str], max_fetches: int, pause_seconds: float, log_path: Path) -> None:
    settings = get_settings()
    for url in urls:
        parse_profile_url(url, max_length=settings.max_url_length)
    cache = CacheStore(settings.cache_database_path, settings.cache_ttl_seconds)
    await cache.open()
    captured = load_captured_endpoints(settings.captured_endpoints_path)
    sessions = SessionManager(settings, cache)
    if not sessions.cookies_loaded():
        print(
            "Set LINKEDIN_COOKIE_JAR (full Cookie header) or LINKEDIN_LI_AT and LINKEDIN_JSESSIONID.",
            file=sys.stderr,
        )
        await cache.close()
        raise SystemExit(2)
    set_progress(False)
    client = LinkedInClient(settings, sessions, captured)
    await client.start()
    registry = QueryRegistry(cache, captured)
    await registry.seed_from_captured()
    discovery = QueryDiscovery(settings, client, registry)
    service = ProfileService(settings, cache, client, registry, discovery)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    ok = 0
    log_path.write_text("", encoding="utf-8")
    try:
        for index in range(max_fetches):
            url = urls[index % len(urls)]
            slug = parse_profile_url(url, max_length=settings.max_url_length)
            hop_started = datetime.now(timezone.utc)
            elapsed = (hop_started - started).total_seconds()
            try:
                response = await service.fetch(url, uuid4(), bypass_cache=True)
                ok += 1
                line = (
                    f"{hop_started.isoformat()} n={index + 1}/{max_fetches} elapsed={elapsed:.0f}s "
                    f"slug={slug} ok visibility={response.profile.visibility} "
                    f"experience={response.sections.get('experience')} "
                    f"education={response.sections.get('education')} "
                    f"skills={response.sections.get('skills')} "
                    f"volunteering={response.sections.get('volunteering')} "
                    f"projects={response.sections.get('projects')} "
                    f"publications={response.sections.get('publications')} "
                    f"honors={response.sections.get('honors')}"
                )
            except AppError as exc:
                line = (
                    f"{hop_started.isoformat()} n={index + 1}/{max_fetches} elapsed={elapsed:.0f}s "
                    f"slug={slug} FAIL {exc.code}"
                )
                print(line, flush=True)
                log_path.write_text(log_path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
                if exc.code in _FATAL_SOAK:
                    print(
                        f"session died after {ok} live fetches in {elapsed:.0f}s ({exc.code})",
                        flush=True,
                    )
                    raise SystemExit(1)
                continue
            print(line, flush=True)
            log_path.write_text(log_path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
            if index + 1 < max_fetches and pause_seconds > 0:
                await asyncio.sleep(pause_seconds)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        print(f"session still valid after {ok}/{max_fetches} live fetches in {elapsed:.0f}s", flush=True)
    finally:
        set_progress(True)
        await client.close()
        await cache.close()
