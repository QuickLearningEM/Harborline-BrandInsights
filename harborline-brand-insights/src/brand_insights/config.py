"""Central configuration, loaded from BI_* environment variables or a .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SEGMENTS = (
    "Established Homeowners",
    "First-Time Furnishers",
    "Design Enthusiasts",
    "Lapsed Customers",
    "Nest & Co. Shoppers",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BI_", env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    # Warehouse
    warehouse_backend: Literal["sqlite", "snowflake"] = "sqlite"
    sqlite_path: Path = Path("data/warehouse.db")
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""  # prefer key-pair auth in production
    snowflake_private_key_path: Path | None = None
    snowflake_role: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = "BRAND_INSIGHTS"
    snowflake_schema: str = "PUBLIC"

    # Ingestion
    landing_dir: Path = Path("data/landing")
    youtube_api_key: str = ""
    youtube_search_terms: str = "Harborline Home,Nest & Co. furniture"
    youtube_max_quota_units: int = 3000

    # Analytics
    revenue_window_days: int = 365
    lapsed_days: int = 540
    min_sentiment_sample: int = 30
    min_attribute_mentions: int = 10
    under_invested_index: float = 120.0
    over_invested_index: float = 80.0
    mismatch_threshold: float = -0.15
    sentiment_classifier: Literal["lexicon", "llm"] = "lexicon"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"

    # Web and security
    session_secret: str = ""
    session_max_age_seconds: int = 8 * 3600
    session_idle_seconds: int = 30 * 60
    secure_cookies: bool = False  # set true when served over HTTPS outside production
    auth_db_path: Path = Path("data/auth.db")
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    forwarded_allow_ips: str = "127.0.0.1"
    login_max_failures: int = 5
    login_lockout_seconds: int = 900
    dashboard_cache_seconds: int = 300

    @property
    def host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.is_production:
            if len(self.session_secret) < 32:
                raise ValueError("BI_SESSION_SECRET must be at least 32 characters in production")
            if "*" in self.host_list:
                raise ValueError("BI_ALLOWED_HOSTS must not contain '*' in production")
        return self

    def session_secret_or_dev(self) -> str:
        """Return the configured secret, or an ephemeral dev-only value outside production."""
        if self.session_secret:
            return self.session_secret
        import secrets

        return secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
