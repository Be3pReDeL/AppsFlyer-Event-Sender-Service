"""Application configuration using pydantic-settings."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["dev", "prod"] = Field(default="dev", description="Application environment")
    app_name: str = Field(default="AppsFlyer Event Sender", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # Authentication
    auth_mode: Literal["token", "hmac"] = Field(default="token", description="Authentication mode")
    api_tokens: str = Field(default="", description="Comma-separated list of valid API tokens")
    hmac_keys_json: str = Field(default="{}", description="JSON mapping of public_id to secret")
    auth_ts_skew_seconds: int = Field(default=300, description="Allowed timestamp skew for HMAC auth")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    stream_main: str = Field(default="events:main", description="Main event stream name")
    stream_dlq: str = Field(default="events:dlq", description="Dead letter queue stream name")

    # Worker
    worker_consumer_group: str = Field(default="af_sender", description="Redis consumer group name")
    worker_consumer_name: str = Field(default="", description="Consumer name (auto-generated if empty)")
    worker_concurrency: int = Field(default=10, description="Max concurrent AppsFlyer requests")
    max_attempts: int = Field(default=8, description="Maximum retry attempts before DLQ")
    backoff_base_seconds: float = Field(default=1.0, description="Base backoff delay in seconds")
    backoff_max_seconds: float = Field(default=60.0, description="Maximum backoff delay in seconds")
    pending_claim_ms: int = Field(default=60000, description="Idle time before reclaiming pending messages")

    # AppsFlyer
    appsflyer_base_url: str = Field(
        default="https://api2.appsflyer.com",
        description="AppsFlyer API base URL",
    )
    appsflyer_timeout_seconds: float = Field(default=5.0, description="AppsFlyer API timeout")
    appsflyer_dev_key: str = Field(default="", description="AppsFlyer dev key for authentication")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_rps: int = Field(default=100, description="Requests per second limit")
    rate_limit_burst: int = Field(default=200, description="Burst limit for rate limiting")

    # Deduplication
    dedup_ttl_seconds: int = Field(default=604800, description="Deduplication key TTL (7 days)")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: Literal["json", "console"] = Field(default="json", description="Log output format")

    @field_validator("api_tokens", mode="before")
    @classmethod
    def validate_api_tokens(cls, v: str) -> str:
        """Ensure api_tokens is a string."""
        if v is None:
            return ""
        return str(v)

    def get_api_tokens_list(self) -> list[str]:
        """Parse comma-separated API tokens into a list."""
        if not self.api_tokens:
            return []
        return [token.strip() for token in self.api_tokens.split(",") if token.strip()]

    def get_hmac_keys(self) -> dict[str, str]:
        """Parse HMAC keys JSON into a dictionary."""
        import json

        if not self.hmac_keys_json or self.hmac_keys_json == "{}":
            return {}
        try:
            return json.loads(self.hmac_keys_json)
        except json.JSONDecodeError:
            return {}


def get_settings() -> Settings:
    """Get settings instance.

    Note: Not cached to ensure environment variable changes are reflected
    in tests and runtime configuration updates.
    """
    return Settings()
