from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FORK_INTELLIGENCE_",
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = "development"
    web_origin: str = "http://localhost:3000"
    database_url: str = Field(
        default=(
            "postgresql+psycopg://fork_intelligence:fork_intelligence@localhost:5432/"
            "fork_intelligence"
        ),
        validation_alias=AliasChoices("FORK_INTELLIGENCE_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("FORK_INTELLIGENCE_REDIS_URL", "REDIS_URL"),
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("FORK_INTELLIGENCE_GITHUB_TOKEN", "GITHUB_TOKEN"),
    )
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    github_graphql_enabled: bool = True
    max_graphql_cost: int = Field(default=50, ge=1, le=1000)
    max_graphql_branches: int = Field(default=100, ge=1, le=100)
    graphql_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    git_store_root: Path = Path(".data/git-networks")
    max_forks: int = Field(default=250, ge=1, le=5000)
    max_github_pages: int = Field(default=5, ge=1, le=50)
    max_github_requests: int = Field(default=100, ge=1, le=1000)
    max_shortlist: int = Field(default=12, ge=1, le=25)
    max_deep_repositories: int = Field(default=12, ge=1, le=25)
    max_branches_per_fork: int = Field(default=3, ge=1, le=25)
    max_analysis_seconds: int = Field(default=2700, ge=60, le=2700)
    max_blob_bytes: int = Field(default=2_000_000, ge=1024, le=50_000_000)
    max_git_store_bytes: int = Field(default=5_000_000_000, ge=1_000_000, le=100_000_000_000)
    analysis_retention_days: int = Field(default=30, ge=1, le=365)
    export_retention_days: int = Field(default=7, ge=1, le=90)
    git_timeout_seconds: float = Field(default=120.0, ge=1, le=1800)
    git_max_output_bytes: int = Field(default=10_000_000, ge=1024, le=100_000_000)
    max_git_commits: int = Field(default=2000, ge=1, le=20_000)
    max_request_body_bytes: int = Field(default=65_536, ge=1024, le=1_000_000)
    max_active_analyses: int = Field(default=10, ge=1, le=100)
    analysis_requests_per_minute: int = Field(default=10, ge=1, le=120)
    min_git_free_bytes: int = Field(default=1_000_000_000, ge=0, le=100_000_000_000)
    sse_poll_seconds: float = Field(default=0.5, ge=0.05, le=10)
    sse_heartbeat_seconds: float = Field(default=15, ge=1, le=60)
    ai_enabled: bool = False

    @field_validator("github_token", mode="before")
    @classmethod
    def empty_github_token_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_github_api_origin(self) -> Settings:
        configured = urlsplit(self.github_api_url)
        canonical = self.github_api_url == "https://api.github.com"
        has_unsafe_url_parts = bool(
            configured.username
            or configured.password
            or configured.port
            or configured.path
            or configured.query
            or configured.fragment
        )
        if canonical:
            return self
        if self.github_token is not None:
            raise ValueError("GitHub tokens may only be sent to https://api.github.com")
        if self.environment.lower() == "production":
            raise ValueError("Production must use the canonical GitHub API origin")
        if configured.scheme != "https" or not configured.hostname or has_unsafe_url_parts:
            raise ValueError("Custom GitHub API origins must be tokenless HTTPS origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
