from __future__ import annotations

from linkedin_profile_api.linkedin.endpoints import CapturedEndpoints, sanitize_headers

ACCEPT_NORMALIZED = "application/vnd.linkedin.normalized+json+2.1"
RESTLI_VERSION = "2.0.0"
DEFAULT_LI_LANG = "en_US"
DEFAULT_PAGE_INSTANCE = "urn:li:page:d_flagship3_profile_view_base;"
DEFAULT_LI_TRACK = (
    '{"clientVersion":"1.13.46267","mpVersion":"1.13.46267","osName":"web",'
    '"timezoneOffset":5.5,"timezone":"Asia/Calcutta","deviceFormFactor":"DESKTOP",'
    '"mpName":"voyager-web","displayDensity":2,"displayWidth":2940,"displayHeight":1912}'
)


def strip_jsessionid_quotes(value: str) -> str:
    return value.strip().strip('"')


def build_request_headers(
    csrf_token: str,
    captured: CapturedEndpoints,
) -> dict[str, str]:
    headers = {
        "accept": ACCEPT_NORMALIZED,
        "csrf-token": strip_jsessionid_quotes(csrf_token),
        "x-restli-protocol-version": RESTLI_VERSION,
        "x-li-lang": DEFAULT_LI_LANG,
        "x-li-track": DEFAULT_LI_TRACK,
        "x-li-page-instance": DEFAULT_PAGE_INSTANCE,
        "x-li-deco-include-micro-schema": "true",
    }
    extra = sanitize_headers(captured.headers)
    for key in ("x-li-lang", "x-li-track", "referer", "x-li-deco-include-micro-schema"):
        value = extra.get(key)
        if value:
            headers[key] = value
    page_instance = extra.get("x-li-page-instance")
    if page_instance and "profile" in page_instance.lower():
        headers["x-li-page-instance"] = page_instance
    return headers
