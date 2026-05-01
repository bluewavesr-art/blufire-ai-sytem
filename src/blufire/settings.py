"""Per-install configuration for Blufire.

Resolution order:
  config.yaml: --config flag → $BLUFIRE_CONFIG → $BLUFIRE_HOME/config.yaml
               → /etc/blufire/config.yaml → ./config.yaml
  .env:        $BLUFIRE_HOME/.env → /etc/blufire/.env → ./.env
"""

from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TenantConfig(BaseModel):
    id: str = Field(..., min_length=1, description="Stable tenant identifier (slug).")
    display_name: str = Field(..., min_length=1)
    timezone: str = "UTC"


class PathsConfig(BaseModel):
    data_dir: Path
    log_dir: Path

    @field_validator("data_dir", "log_dir", mode="before")
    @classmethod
    def _expand(cls, v: Any) -> Any:
        if isinstance(v, str):
            return Path(os.path.expandvars(os.path.expanduser(v)))
        return v


class SenderConfig(BaseModel):
    name: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    reply_to: str | None = None
    physical_address: str = Field(
        ...,
        min_length=10,
        description="Required for CAN-SPAM. Full mailing address shown in every email footer.",
    )


class ModelsConfig(BaseModel):
    default: str = "claude-sonnet-4-20250514"
    drafting: str | None = None
    scoring: str | None = None

    def for_role(self, role: Literal["default", "drafting", "scoring"]) -> str:
        return getattr(self, role) or self.default


class ProspectSearch(BaseModel):
    name: str
    person_titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    per_page: int = Field(default=10, ge=1, le=100)


class SendWindow(BaseModel):
    start: time = time(8, 0)
    end: time = time(17, 0)
    days: list[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])


class WebhookConfig(BaseModel):
    gmail_draft_url: HttpUrl | None = None


class OutreachConfig(BaseModel):
    daily_send_cap: int = Field(default=50, ge=0, le=500)
    per_domain_daily_cap: int = Field(default=5, ge=0, le=100)
    send_window: SendWindow = SendWindow()
    system_prompt_path: Path | None = None
    webhook: WebhookConfig = WebhookConfig()


class ComplianceConfig(BaseModel):
    unsubscribe_base_url: HttpUrl | None = None
    legal_basis: Literal["consent", "legitimate_interest"] = "legitimate_interest"
    jurisdiction: list[str] = Field(default_factory=lambda: ["US"])
    suppression_db: Path | None = None
    exclude_eea: bool = True
    run_unsubscribe_server: bool = False


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "console"] = "json"
    file: Path | None = None
    rotate_max_bytes: int = 50 * 1024 * 1024
    rotate_backup_count: int = 10


class _Secrets(BaseSettings):
    """Secrets only — sourced from environment / .env."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    hubspot_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    apollo_api_key: SecretStr | None = None
    gmail_user: str | None = None
    gmail_app_password: SecretStr | None = None
    make_draft_webhook_url: HttpUrl | None = None
    unsubscribe_base_url: HttpUrl | None = None
    blufire_license_key: SecretStr | None = None
    sentry_dsn: str | None = None


class Settings(BaseModel):
    tenant: TenantConfig
    paths: PathsConfig
    sender: SenderConfig
    models: ModelsConfig = ModelsConfig()
    prospect_searches: list[ProspectSearch] = Field(default_factory=list)
    outreach: OutreachConfig = OutreachConfig()
    compliance: ComplianceConfig = ComplianceConfig()
    logging: LoggingConfig = LoggingConfig()
    secrets: _Secrets = Field(default_factory=_Secrets)

    @property
    def suppression_db_path(self) -> Path:
        return self.compliance.suppression_db or (self.paths.data_dir / "suppression.sqlite")

    @property
    def send_log_db_path(self) -> Path:
        return self.paths.data_dir / "send_log.sqlite"

    @property
    def consent_log_db_path(self) -> Path:
        return self.paths.data_dir / "consent_log.sqlite"


def _candidate_config_paths(explicit: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    if env_cfg := os.environ.get("BLUFIRE_CONFIG"):
        candidates.append(Path(env_cfg))
    if home := os.environ.get("BLUFIRE_HOME"):
        candidates.append(Path(home) / "config.yaml")
    candidates.append(Path("/etc/blufire/config.yaml"))
    candidates.append(Path.cwd() / "config.yaml")
    return candidates


def _candidate_env_paths() -> list[Path]:
    candidates: list[Path] = []
    if home := os.environ.get("BLUFIRE_HOME"):
        candidates.append(Path(home) / ".env")
    candidates.append(Path("/etc/blufire/.env"))
    candidates.append(Path.cwd() / ".env")
    return candidates


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Top-level of {path} must be a mapping, got {type(data).__name__}")
    return data


def _interpolate(value: Any, env: dict[str, str]) -> Any:
    """Replace ${VAR} placeholders in strings, recursively. Raises on missing vars."""
    if isinstance(value, str):
        return os.path.expandvars(value).replace("$$", "$")
    if isinstance(value, dict):
        return {k: _interpolate(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, env) for v in value]
    return value


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from disk. Loads .env files first so YAML interpolation can use them."""
    for env_file in _candidate_env_paths():
        if env_file.is_file():
            load_dotenv(env_file, override=False)

    chosen: Path | None = None
    for candidate in _candidate_config_paths(config_path):
        if candidate.is_file():
            chosen = candidate
            break
    if chosen is None:
        searched = ", ".join(str(p) for p in _candidate_config_paths(config_path))
        raise FileNotFoundError(
            f"Blufire config.yaml not found. Searched: {searched}. "
            f"Set BLUFIRE_CONFIG or place a config.yaml in $BLUFIRE_HOME or /etc/blufire."
        )

    raw = _interpolate(_load_yaml(chosen), dict(os.environ))
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid Blufire config at {chosen}:\n{exc}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached entry point. Tests can override by calling get_settings.cache_clear()."""
    return load_settings()


def reset_settings_cache() -> None:
    """Clear the singleton (used by tests)."""
    get_settings.cache_clear()
