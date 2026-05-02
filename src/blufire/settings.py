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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class TenantConfig(BaseModel):
    id: str = Field(..., min_length=1, description="Stable tenant identifier (slug).")
    display_name: str = Field(..., min_length=1)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"unknown timezone: {v!r}. Use an IANA name (e.g. 'America/Chicago')."
            ) from exc
        return v


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


# Supported provider identifiers. Adding a new CRM/email backend means:
#   1. Implementing the matching Tool classes under runtime/tools/<provider>.py
#      with a module-level ``register(tools)`` function.
#   2. Adding the new identifier to ``CRM_PROVIDERS`` / ``EMAIL_PROVIDERS``
#      in runtime/bootstrap.py.
#   3. Adding the literal here so configs validate at parse time.
#
# Note: GHL (GoHighLevel) is both a CRM AND an email/SMS sender, so a GHL
# tenant typically sets ``crm.provider=ghl`` AND ``email.provider=ghl``.
# The provider modules are independent — register() is called for whichever
# is configured.
CrmProvider = Literal["hubspot", "jobber", "acculynx", "servicetitan", "ghl", "gsheets"]
EmailProvider = Literal["gmail", "mailgun", "sendgrid", "ses", "ghl"]
EmailDraftProvider = Literal["make_webhook", "gmail_api", "outlook_api", "ghl", "gsheets"]
ProspectProvider = Literal["apollo", "gplaces", "zoominfo", "lusha"]
EnrichProvider = Literal["website", "hunter", "apollo"]


class EnrichConfig(BaseModel):
    """Email-enrichment provider used after the prospect search returns a
    lead with no email. Set to ``"website"`` to scrape the lead's website
    for ``mailto:`` links and obvious email patterns."""

    provider: EnrichProvider = "website"


class CrmConfig(BaseModel):
    provider: CrmProvider = "hubspot"


class EmailConfig(BaseModel):
    """Two independent contracts:

    * ``provider`` selects the immediate-send backend (``email.send_smtp``).
    * ``draft_provider`` selects the draft-creation backend
      (``email.create_draft``).

    A tenant may use Mailgun for sends and a Make.com webhook for drafts;
    they're not coupled."""

    provider: EmailProvider = "gmail"
    draft_provider: EmailDraftProvider = "make_webhook"


class ProspectConfig(BaseModel):
    provider: ProspectProvider = "apollo"


class GSheetsConfig(BaseModel):
    """Sheet-as-CRM configuration. Used when ``crm.provider == "gsheets"``
    and/or ``email.draft_provider == "gsheets"``.

    The ``leads_*`` worksheet is the source-of-truth for contacts (dedup
    via ``crm.search_contacts``, append via ``crm.create_contact``). The
    ``drafts_*`` worksheet is where ``email.create_draft`` appends new
    drafts for human review. The ``call_list_*`` worksheet is where the
    daily_lead_gen orchestrator routes leads with no email so the team
    can phone them instead."""

    spreadsheet_url: HttpUrl | None = None
    leads_worksheet: str = "Leads"
    drafts_worksheet: str = "Drafts"
    call_list_worksheet: str = "Call List"


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
    gsheets_credentials_path: Path | None = None
    gplaces_api_key: SecretStr | None = None

    @field_validator(
        "make_draft_webhook_url", "unsubscribe_base_url", mode="before"
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Treat empty-string env var values as absent (None).
        Operators commonly leave placeholder lines like UNSUBSCRIBE_BASE_URL=""
        in .env files; pydantic-settings passes the empty string through and
        the URL validator then rejects it."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class Settings(BaseModel):
    tenant: TenantConfig
    paths: PathsConfig
    sender: SenderConfig
    models: ModelsConfig = ModelsConfig()
    prospect_searches: list[ProspectSearch] = Field(default_factory=list)
    crm: CrmConfig = CrmConfig()
    email: EmailConfig = EmailConfig()
    prospect: ProspectConfig = ProspectConfig()
    enrich: EnrichConfig = EnrichConfig()
    gsheets: GSheetsConfig = GSheetsConfig()
    outreach: OutreachConfig = OutreachConfig()
    compliance: ComplianceConfig = ComplianceConfig()
    logging: LoggingConfig = LoggingConfig()
    secrets: _Secrets = Field(default_factory=_Secrets)

    @model_validator(mode="after")
    def _require_webhook_when_prospects_configured(self) -> Settings:
        # If the install has prospect searches defined, the daily-leadgen flow
        # WILL run; refuse to load if its draft sink is unreachable. Only the
        # make_webhook draft provider needs a webhook URL — gsheets and others
        # have their own sink config validated elsewhere.
        if (
            self.prospect_searches
            and self.email.draft_provider == "make_webhook"
            and self.outreach.webhook.gmail_draft_url is None
        ):
            raise ValueError(
                "prospect_searches are configured with email.draft_provider='make_webhook' "
                "but outreach.webhook.gmail_draft_url is empty. Set MAKE_DRAFT_WEBHOOK_URL "
                "in .env or outreach.webhook.gmail_draft_url in config.yaml."
            )
        return self

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


def _candidate_env_paths(config_path: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if home := os.environ.get("BLUFIRE_HOME"):
        candidates.append(Path(home) / ".env")
    # Tenant-specific .env: same dir + stem as the config yaml.
    # Works for both explicit paths and $BLUFIRE_CONFIG.
    cfg = config_path or (
        Path(os.environ["BLUFIRE_CONFIG"]) if "BLUFIRE_CONFIG" in os.environ else None
    )
    if cfg is not None:
        candidates.append(Path(cfg).with_suffix(".env"))
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
    for env_file in _candidate_env_paths(config_path):
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
