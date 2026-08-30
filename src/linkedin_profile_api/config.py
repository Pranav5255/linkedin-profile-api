from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    api_key: str = ""
    demo_api_key: str = ""
    linkedin_li_at: str = ""
    linkedin_jsessionid: str = ""
    linkedin_li_at_failover: str = ""
    linkedin_jsessionid_failover: str = ""
    linkedin_cookie_jar: str = ""
    linkedin_cookie_jar_failover: str = ""
    linkedin_egress_proxy: str = ""
    linkedin_impersonate: str = "chrome124"
    cache_database_path: Path = Path("data/cache.db")
    cache_ttl_seconds: int = 21_600
    max_upstream_concurrency: int = 1
    upstream_timeout_seconds: float = 90
    request_deadline_seconds: float = 360
    upstream_delay_ms_min: int = 800
    upstream_delay_ms_max: int = 2_000
    bundle_fetch_timeout_seconds: float = 8
    bundle_max_bytes: int = 2_097_152
    bundle_max_assets: int = 6
    session_stale_after_seconds: int = 900
    session_probe_interval_seconds: int = 300
    linkedin_decoy_feed: bool = False
    captured_endpoints_path: Path = Path("data/captured-endpoints.json")
    log_level: str = "INFO"
    duckdns_hostname: str = ""

    evaluator_quota_per_hour: int = Field(default=60)
    demo_quota_per_hour: int = Field(default=5)
    max_request_body_bytes: int = Field(default=32_768)
    max_url_length: int = Field(default=512)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
