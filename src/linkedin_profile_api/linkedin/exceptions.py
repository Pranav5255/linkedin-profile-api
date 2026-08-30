class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)


class InvalidApiKeyError(AppError):
    status_code = 401
    code = "invalid_api_key"
    message = "Missing or invalid API key."


class InvalidProfileUrlError(AppError):
    status_code = 422
    code = "invalid_profile_url"
    message = "The profile URL is not an accepted LinkedIn /in/ URL."


class ProfileNotFoundError(AppError):
    status_code = 404
    code = "profile_not_found"
    message = "The LinkedIn profile was not found."


class LocalRateLimitedError(AppError):
    status_code = 429
    code = "local_rate_limited"
    message = "Local rate limit exceeded."


class LinkedInRateLimitedError(AppError):
    status_code = 429
    code = "linkedin_rate_limited"
    message = "LinkedIn rate-limited the upstream request."


class LinkedInProtocolChangedError(AppError):
    status_code = 502
    code = "linkedin_protocol_changed"
    message = "LinkedIn returned an unexpected response shape."


class LinkedInSessionExpiredError(AppError):
    status_code = 503
    code = "linkedin_session_expired"
    message = (
        "LinkedIn rejected the session. Copy a fresh Cookie header from the "
        "browser tab that can open the profile, replace LINKEDIN_COOKIE_JAR, "
        "and close that tab before retrying."
    )


class LinkedInBlockedError(AppError):
    status_code = 503
    code = "linkedin_blocked"
    message = "LinkedIn blocked the upstream request."


class UpstreamTimeoutError(AppError):
    status_code = 504
    code = "upstream_timeout"
    message = "A LinkedIn request timed out."


class UpstreamDeadlineError(AppError):
    status_code = 504
    code = "upstream_deadline"
    message = "The request deadline expired before identity resolution."


class SectionFetchError(Exception):
    """A single optional section failed; the rest of the profile can still succeed."""
