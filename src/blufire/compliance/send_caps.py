"""Daily send caps + audit log. SQLite-backed.

Single ``send_log`` table doubles as the audit trail (who, when, subject hash).
Email subject is hashed — never stored in plaintext, so a compromised log can't
leak campaign content. Body is never stored.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from blufire.compliance._db import connect, domain_of, normalize_email
from blufire.logging_setup import get_logger
from blufire.settings import OutreachConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    sent_at_date TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    recipient_domain TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_send_log_date ON send_log(tenant_id, sent_at_date);
CREATE INDEX IF NOT EXISTS idx_send_log_domain
    ON send_log(tenant_id, sent_at_date, recipient_domain);
"""


_DAY_NAMES = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


@dataclass(frozen=True)
class CapDecision:
    allowed: bool
    reason: str | None = None


class SendCapStore:
    def __init__(self, db_path: Path, tenant_id: str, outreach: OutreachConfig) -> None:
        self._db = db_path
        self._tenant = tenant_id
        self._cfg = outreach
        self._log = get_logger("blufire.compliance.send_caps").bind(tenant_id=tenant_id)
        with connect(self._db) as conn:
            conn.executescript(_SCHEMA)

    def _now(self, tz_name: str) -> dt.datetime:
        try:
            return dt.datetime.now(ZoneInfo(tz_name))
        except Exception:
            return dt.datetime.now(dt.UTC)

    def can_send(self, email: str, *, tz_name: str = "UTC") -> CapDecision:
        norm = normalize_email(email)
        domain = domain_of(norm)
        now = self._now(tz_name)
        today = now.date().isoformat()

        if not self._in_window(now):
            return CapDecision(False, "outside_send_window")

        with connect(self._db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM send_log WHERE tenant_id = ? AND sent_at_date = ?",
                (self._tenant, today),
            ).fetchone()[0]
            if total >= self._cfg.daily_send_cap:
                return CapDecision(False, "daily_cap_reached")
            per_domain = conn.execute(
                """
                SELECT COUNT(*) FROM send_log
                WHERE tenant_id = ? AND sent_at_date = ? AND recipient_domain = ?
                """,
                (self._tenant, today, domain),
            ).fetchone()[0]
            if per_domain >= self._cfg.per_domain_daily_cap:
                return CapDecision(False, "per_domain_cap_reached")
        return CapDecision(True)

    def record_send(self, email: str, *, subject: str, source: str, tz_name: str = "UTC") -> None:
        norm = normalize_email(email)
        domain = domain_of(norm)
        now = self._now(tz_name)
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
        with connect(self._db) as conn:
            conn.execute(
                """
                INSERT INTO send_log (
                    sent_at, sent_at_date, tenant_id, recipient,
                    recipient_domain, subject_hash, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now.isoformat(),
                    now.date().isoformat(),
                    self._tenant,
                    norm,
                    domain,
                    subject_hash,
                    source,
                ),
            )

    def _in_window(self, now: dt.datetime) -> bool:
        window = self._cfg.send_window
        day = now.strftime("%a")
        if window.days and day not in window.days:
            return False
        current = now.time().replace(microsecond=0)
        return window.start <= current <= window.end
