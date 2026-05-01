"""Consent / legal-basis log. Backed by SQLite. Stores the basis on which we
contacted each prospect plus an evidence hash (e.g., Apollo enrichment payload)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blufire.compliance._db import connect, normalize_email

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    basis TEXT NOT NULL,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    UNIQUE (email, tenant_id, basis)
);
"""


@dataclass(frozen=True)
class ConsentRecord:
    email: str
    basis: str
    source: str
    recorded_at: str
    evidence_hash: str


class ConsentLog:
    def __init__(self, db_path: Path, tenant_id: str) -> None:
        self._db = db_path
        self._tenant = tenant_id
        with connect(self._db) as conn:
            conn.executescript(_SCHEMA)

    def record(
        self,
        email: str,
        *,
        basis: str,
        source: str,
        evidence: Any,
    ) -> ConsentRecord:
        norm = normalize_email(email)
        ev_bytes = json.dumps(evidence, sort_keys=True, default=str).encode("utf-8")
        ev_hash = hashlib.sha256(ev_bytes).hexdigest()
        now = dt.datetime.now(dt.UTC).isoformat()
        with connect(self._db) as conn:
            conn.execute(
                """
                INSERT INTO consent_log (
                    email, tenant_id, basis, source, recorded_at, evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email, tenant_id, basis) DO UPDATE SET
                    source = excluded.source,
                    recorded_at = excluded.recorded_at,
                    evidence_hash = excluded.evidence_hash
                """,
                (norm, self._tenant, basis, source, now, ev_hash),
            )
        return ConsentRecord(
            email=norm,
            basis=basis,
            source=source,
            recorded_at=now,
            evidence_hash=ev_hash,
        )
