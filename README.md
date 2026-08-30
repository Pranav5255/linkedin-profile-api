# LinkedIn Profile API

Hosted HTTPS API that accepts a LinkedIn `/in/{slug}` profile URL and returns structured JSON. The backend talks to LinkedIn Voyager / GraphQL HTTP endpoints with a browser-like TLS fingerprint. There is no browser, Playwright, Selenium, or Puppeteer in this project.

This is a take-home assignment implementation. LinkedIn’s User Agreement prohibits scraping, unauthorized automation, and reverse engineering. Using a personal `li_at` session can get the account restricted. Do not use a primary career account.

## Architecture

```text
Client --HTTPS:443--> Caddy --> FastAPI :8000
                                ├── curl_cffi AsyncSession (impersonate=chrome124)
                                ├── URL → slug → URN resolver
                                ├── queryId / decorationId discovery
                                ├── Normalized JSON URN resolver
                                ├── Visibility / redaction detector
                                └── SQLite TTL cache
```

Stack: Python 3.12, FastAPI, Pydantic v2, `curl_cffi==0.13.0`, SQLite WAL. TLS impersonation is necessary but not sufficient — LinkedIn also scores IP reputation, cadence, and cookies.

## Supported fields

Returned when LinkedIn returns them **and** the backend session can see them:

- name, headline, location, industry, about
- profile and background images (URLs only; they expire)
- experience, education, skills, certifications, languages
- volunteering, projects, publications, honors when present

`profile.visibility`: `full` | `limited` | `out_of_network` | `unknown`.

Section states: `available` | `empty` | `inaccessible` | `upstream_changed` | `failed`.

`"LinkedIn Member"` is treated as `out_of_network` / `inaccessible`, never as a blank successful parse.

## Local Python install

Requires Python 3.12+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
# fill API_KEY and LINKEDIN_COOKIE_JAR (or LI_AT + JSESSIONID)
linkedin-profile-api serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` and use **Authorize** with `X-API-Key`.

## Local Docker install

```bash
cp .env.example .env
docker compose up --build api
```

The API listens on `http://127.0.0.1:8000` only. `docker compose up --build` also starts Caddy on 80/443 in front of it.

## Environment variables

See `.env.example`. All values are empty placeholders in git.

| Variable | Purpose |
|---|---|
| `API_KEY` | Evaluator key (private). |
| `DEMO_API_KEY` | Optional low-quota key (5 req/hour). |
| `LINKEDIN_COOKIE_JAR` | Full Cookie header from a logged-in browser. Preferred. |
| `LINKEDIN_LI_AT` / `LINKEDIN_JSESSIONID` | Optional overrides if you are not pasting the full jar. |
| `LINKEDIN_COOKIE_JAR_FAILOVER` | Optional second aged session (full jar). |
| `LINKEDIN_LI_AT_FAILOVER` / `LINKEDIN_JSESSIONID_FAILOVER` | Optional failover overrides. |
| `LINKEDIN_EGRESS_PROXY` | Optional sticky residential/ISP proxy URL. Use when the host IP is blocked or challenged. |
| `LINKEDIN_IMPERSONATE` | curl_cffi target. Default `chrome124`. Match the browser you copied cookies from. |
| `CACHE_DATABASE_PATH` | SQLite path. Default `/data/cache.db` in Docker. |
| `CACHE_TTL_SECONDS` | Default 21600 (6 hours). |
| `REQUEST_DEADLINE_SECONDS` | Whole-request budget. Default 360. |
| `UPSTREAM_TIMEOUT_SECONDS` | Per LinkedIn call. Default 90. |
| `UPSTREAM_DELAY_MS_MIN` / `MAX` | Jitter between LinkedIn calls. Default 800–2000. |
| `SESSION_PROBE_INTERVAL_SECONDS` | Min gap between `/voyager/api/me` probes from `/readyz`. Default 300. |
| `LINKEDIN_DECOY_FEED` | After `/me`, hit `/feed/updatesV2` before the profile call. Default false. |
| `CAPTURED_ENDPOINTS_PATH` | Gitignored output of HAR import. |

Never put cookies or keys in the README, image, or git history.

## API

All profile routes require `X-API-Key`. The header is registered as an OpenAPI security scheme so `/docs` → Authorize works.

```http
POST /v1/profiles
X-API-Key: <key>
Content-Type: application/json

{"profile_url":"https://www.linkedin.com/in/example-profile/"}
```

```http
GET /v1/profiles?url=https://www.linkedin.com/in/example-profile/
X-API-Key: <key>
```

Accepted URLs: `https://linkedin.com/in/{slug}` and `https://www.linkedin.com/in/{slug}` only. Query and fragment are stripped. The service never fetches the user-supplied URL.

```http
GET /healthz    # process alive; never calls LinkedIn
GET /readyz     # cookies + cache; live `/voyager/api/me` at most once per SESSION_PROBE_INTERVAL_SECONDS
GET /docs
GET /openapi.json
```

### Errors

| Status | `error.code` |
|---|---|
| 401 | `invalid_api_key` |
| 422 | `invalid_profile_url` |
| 404 | `profile_not_found` |
| 429 | `local_rate_limited` or `linkedin_rate_limited` |
| 502 | `linkedin_protocol_changed` |
| 503 | `linkedin_session_expired` or `linkedin_blocked` (HTTP 999) |
| 504 | `upstream_timeout` or `upstream_deadline` |

Example profile URL for demos: use a 1st- or 2nd-degree profile from the backend account. A random public URL will often return `visibility: out_of_network`.

## Capture (required before a useful spike)

1. Log in to the aged LinkedIn account in a normal browser.
2. Open DevTools → Network.
3. Open a 1st- or 2nd-degree profile and expand every section.
4. Save all as HAR.
5. Repeat for one out-of-network / `"LinkedIn Member"` profile.
6. Import (cookies and CSRF headers are stripped before write):

```bash
linkedin-profile-api capture import path/to/profile.har
linkedin-profile-api capture import path/to/out-of-network.har
```

This writes `data/captured-endpoints.json` (gitignored). `samples/captured-endpoints.example.json` is the redacted committed shape.

Local spike:

```bash
linkedin-profile-api spike --url 'https://www.linkedin.com/in/your-first-degree-slug/'
```

## Reverse-engineering approach

- Session cookies only. Prefer the full jar (`li_at`, `JSESSIONID`, `bcookie`, `lidc`, PerimeterX `_px3` / `_pxvid` / `pxcts`). `csrf-token` is `JSESSIONID` with quotes stripped.
- The HTTP client seeds the cookie jar once and keeps LinkedIn `Set-Cookie` updates (`lidc`, etc.).
- `Accept: application/vnd.linkedin.normalized+json+2.1` plus `x-restli-protocol-version: 2.0.0`.
- `x-li-track` / `x-li-lang` have browser-shaped defaults; a HAR import overrides them.
- Identity: resolve `/in/{slug}` to `urn:li:fsd_profile:...` from the profile page HTML (cached afterwards), then `GET /voyager/api/identity/dash/profiles/{urn}` with `FullProfileWithEntities-93`. `FullProfile-76` is the browser top-card call and returns name/photo only; if it is tried first and has no Position/Education/Skill entities, the client continues to `-93`. `WebTopCardCore-16` is the last fallback. The current web app does not send `q=memberIdentity` with a vanity slug. Section GraphQL runs only when a captured `queryId` exists. The old `/identity/profiles/{id}/profileView` path returns 410.
- Normalized JSON is a flat `included[]` graph. `*`-prefixed keys are URN pointers. Resolution is separate from field extraction, with a cycle guard and depth limit.
- `queryId` hashes rotate with LinkedIn web bundles. On operation-specific 400/500 the client invalidates once, scrapes allowlisted `*.licdn.com` JS assets, and rediscovers once. Discovery is skipped when the request deadline is close.

## Cache and cookie rotation

SQLite tables: `profile_cache`, `identity_cache`, `query_registry`, `session_state`. Auth failures, challenge HTML, and HTTP 999 are not cached. Out-of-network responses may be cached briefly and are never served as `full`.

### Rotation runbook (~2 minutes)

1. Log in to the aged account in a normal browser (same country as the egress IP).
2. DevTools → Application → Cookies → `https://www.linkedin.com`. Copy the full Cookie header from any Voyager request in the Network tab.
3. Paste it into `LINKEDIN_COOKIE_JAR`. If LinkedIn hangs or challenges from this host, also set `LINKEDIN_EGRESS_PROXY` to a sticky residential URL.
4. Replace values in the host env file (`chmod 600`).
5. `docker compose up -d --force-recreate api` (Caddy stays up; certs persist).
6. Confirm `/readyz` is ready and a known 1st/2nd-degree profile returns `visibility: full`.

Failover cookies switch once per process on session death. `/readyz` then reports not ready if the last real upstream outcome was a challenge.

## Security

- Constant-time API key compare; evaluator vs demo quotas.
- SSRF: only `/in/{slug}` hosts; bundle fetches limited to `https://*.licdn.com` with size and timeout caps.
- No debug or raw-upstream endpoints.
- Structured JSON logs: request id, status, duration, cache hit, section states, `deadline_hit`, visibility. Never cookies, keys, full profiles, or upstream bodies.

## HTTPS deploy

Clone the repo onto the host. Keep secrets in `.env` (`chmod 600`) and out of git.

If the host is dedicated to this API:

```bash
docker compose up -d --build
```

Caddy terminates TLS on 80/443. Set `DUCKDNS_HOSTNAME` to the public hostname.

If 80/443 are already in use, do not start Caddy. Bind the API on loopback and add a separate nginx `server_name`:

```bash
docker compose -f compose.vm.yaml up -d --build
sudo cp deploy/nginx-linkedin-duckdns.conf /etc/nginx/sites-available/linkedin-duckdns
# replace YOUR_DUCKDNS_HOST in that file, then:
sudo ln -sf /etc/nginx/sites-available/linkedin-duckdns /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d YOUR_DUCKDNS_HOST
```

`compose.vm.yaml` publishes `127.0.0.1:8080` only. Probe `/healthz` after deploy. Do not poll `/readyz` as a keep-alive — it may call `/voyager/api/me` when the last probe is older than `SESSION_PROBE_INTERVAL_SECONDS`.

```text
https://<hostname>/v1/profiles
https://<hostname>/docs
```

## Known limitations

- Voyager `queryId` / `decorationId` values rotate without notice.
- Out-of-network and privacy-restricted profiles return withheld fields (`LinkedIn Member`).
- `li_at` expires or is challenged; use the rotation runbook. Two cookies alone usually die within a minute without PerimeterX cookies.
- Datacenter IP reputation typically hangs instead of returning JSON. Use `LINKEDIN_EGRESS_PROXY` when that happens.
- Image URLs expire.
- Request deadline (360s) can return partial results with `deadline_hit: true`.
- This project violates LinkedIn’s User Agreement if used against LinkedIn. Account risk is real.

## Publication (you do this)

This working copy is local-only. Do not push until you have:

1. Grepped the tree **and** `git log -p` for `li_at`, `JSESSIONID`, API keys, emails, passwords.
2. Confirmed `.env.example` is placeholders and `data/captured-endpoints.json` / `*.har` are ignored.
3. Built from a fresh local clone path (`docker compose build`).
4. Created the GitHub repo yourself and pushed yourself.
5. Sent the evaluator key privately — not in this README.
