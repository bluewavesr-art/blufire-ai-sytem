"""Structured JSON logging with secret redaction.

Use ``configure(settings)`` once at process start, then::

    from blufire.logging_setup import get_logger
    log = get_logger(__name__).bind(tenant_id=settings.tenant.id, run_id=run_id)
    log.info("agent_started", agent="email_outreach")
"""

from __future__ import annotations

import hashlib
import logging
import logging.handlers
import re
import sys
import uuid
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from blufire.settings import Settings


_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+")
_API_KEY_KEYS = {
    "anthropic_api_key",
    "hubspot_api_key",
    "apollo_api_key",
    "gmail_app_password",
    "gmail_password",
    "password",
    "api_key",
    "secret",
    "token",
    "authorization",
}
_REDACTION = "***REDACTED***"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _BEARER_RE.sub(r"\1" + _REDACTION, value)
    return value


def _scrub_processor(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact secret-shaped fields by key name and Bearer tokens by content."""
    for key in list(event_dict.keys()):
        if key.lower() in _API_KEY_KEYS:
            event_dict[key] = _REDACTION
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def hash_recipient(email: str) -> str:
    """Hash a recipient address for log fields. Never log raw emails."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def configure(settings: Settings | None = None) -> None:
    """Idempotently configure stdlib + structlog. Safe to call multiple times."""
    level_name = settings.logging.level if settings else "INFO"
    fmt = settings.logging.format if settings else "json"
    log_file = settings.logging.file if settings else None
    if settings and not log_file:
        log_file = settings.paths.log_dir / "blufire.log"

    level = getattr(logging, level_name)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=settings.logging.rotate_max_bytes if settings else 50 * 1024 * 1024,
                backupCount=settings.logging.rotate_backup_count if settings else 10,
                encoding="utf-8",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        handler.setLevel(level)
        root.addHandler(handler)
    root.setLevel(level)

    renderer: structlog.types.Processor
    if fmt == "console":
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.dict_tracebacks,
            _scrub_processor,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if settings and settings.secrets.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry_sdk.init(
                dsn=settings.secrets.sentry_dsn,
                send_default_pii=False,
                integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
            )
        except ImportError:
            pass


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def new_run_id() -> str:
    """A UUID4 for one invocation; bind into the logger context."""
    return str(uuid.uuid4())
