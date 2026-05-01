"""Suppression list (DNC). Email or domain-level. Backed by SQLite."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from blufire.compliance._db import connect, domain_of, normalize_email
from blufire.logging_setup import get_logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppression (
    email TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    added_at TEXT NOT NULL,
    tenant_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS domain_suppression (
    domain TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    added_at TEXT NOT NULL,
    tenant_id TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SuppressionEntry:
    email: str
    reason: str
    source: str


class SuppressionList:
    def __init__(self, db_path: Path, tenant_id: str) -> None:
        self._db = db_path
        self._tenant = tenant_id
        self._log = get_logger("blufire.compliance.suppression").bind(tenant_id=tenant_id)
        with connect(self._db) as conn:
            conn.executescript(_SCHEMA)

    def is_suppressed(self, email: str) -> bool:
        norm = normalize_email(email)
        try:
            domain = domain_of(norm)
        except ValueError:
            return True  # malformed → always block
        with connect(self._db) as conn:
            row = conn.execute("SELECT 1 FROM suppression WHERE email = ?", (norm,)).fetchone()
            if row is not None:
                return True
            row = conn.execute(
                "SELECT 1 FROM domain_suppression WHERE domain = ?", (domain,)
            ).fetchone()
            return row is not None

    def add(self, email: str, *, reason: str, source: str = "manual") -> None:
        norm = normalize_email(email)
        now = dt.datetime.now(dt.UTC).isoformat()
        with connect(self._db) as conn:
            conn.execute(
                """
                INSERT INTO suppression (email, reason, source, added_at, tenant_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    added_at = excluded.added_at
                """,
                (norm, reason, source, now, self._tenant),
            )
        self._log.info("suppression_added", reason=reason, source=source)

    def add_domain(self, domain: str, *, reason: str) -> None:
        d = domain.strip().lower()
        now = dt.datetime.now(dt.UTC).isoformat()
        with connect(self._db) as conn:
            conn.execute(
                """
                INSERT INTO domain_suppression (domain, reason, added_at, tenant_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET reason = excluded.reason
                """,
                (d, reason, now, self._tenant),
            )

    def import_csv(self, path: Path, *, source: str = "csv-import") -> int:
        """Bulk import from a CSV with a single ``email`` column (header optional)."""
        added = 0
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row:
                    continue
                value = row[0].strip()
                if not value or value.lower() == "email":
                    continue
                self.add(value, reason="bulk import", source=source)
                added += 1
        return added
