from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

from blufire.compliance.consent import ConsentLog


def test_record_basic(tmp_path: Path) -> None:
    log = ConsentLog(tmp_path / "consent.sqlite", "tenant1")
    rec = log.record(
        "alice@example.com",
        basis="legitimate_interest",
        source="apollo-search",
        evidence={"contact_id": "100"},
    )
    assert rec.email == "alice@example.com"
    assert rec.basis == "legitimate_interest"
    assert len(rec.evidence_hash) == 64  # sha256 hex


def test_evidence_hash_stable_with_datetime(tmp_path: Path) -> None:
    """default=str converter handles non-JSON-native types deterministically."""
    log = ConsentLog(tmp_path / "consent.sqlite", "tenant1")
    fixed = dt.datetime(2026, 1, 15, 12, 0, 0, tzinfo=dt.UTC)
    a = log.record(
        "a@x.test",
        basis="consent",
        source="form",
        evidence={"opt_in_at": fixed, "amount": Decimal("9.99")},
    )
    b = log.record(
        "a@x.test",
        basis="consent",
        source="form",
        evidence={"amount": Decimal("9.99"), "opt_in_at": fixed},  # different key order
    )
    # sort_keys=True in dumps means order-independent → same hash
    assert a.evidence_hash == b.evidence_hash


def test_record_upserts_on_same_basis(tmp_path: Path) -> None:
    log = ConsentLog(tmp_path / "consent.sqlite", "tenant1")
    log.record("a@x.test", basis="consent", source="s1", evidence={"v": 1})
    rec = log.record("a@x.test", basis="consent", source="s2", evidence={"v": 2})
    # source updated; hash differs because evidence differs
    assert rec.source == "s2"
