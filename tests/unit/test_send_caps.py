from __future__ import annotations

from pathlib import Path

from blufire.compliance.send_caps import SendCapStore
from blufire.settings import OutreachConfig, SendWindow


def _store(tmp_path: Path, **overrides) -> SendCapStore:
    cfg = OutreachConfig(**overrides) if overrides else OutreachConfig()
    return SendCapStore(tmp_path / "send_log.sqlite", "tenant1", cfg)


def test_daily_cap_blocks_after_n_sends(tmp_path: Path) -> None:
    store = _store(tmp_path, daily_send_cap=2, per_domain_daily_cap=10)
    assert store.can_send("a@x.test", tz_name="UTC").allowed
    store.record_send("a@x.test", subject="hi", source="t")
    store.record_send("b@y.test", subject="hi", source="t")
    blocked = store.can_send("c@z.test", tz_name="UTC")
    assert not blocked.allowed
    assert blocked.reason == "daily_cap_reached"


def test_per_domain_cap(tmp_path: Path) -> None:
    store = _store(tmp_path, daily_send_cap=100, per_domain_daily_cap=2)
    store.record_send("a@x.test", subject="s", source="t")
    store.record_send("b@x.test", subject="s", source="t")
    blocked = store.can_send("c@x.test", tz_name="UTC")
    assert not blocked.allowed
    assert blocked.reason == "per_domain_cap_reached"
    # Other domain still allowed.
    assert store.can_send("c@other.test", tz_name="UTC").allowed


def test_send_window_blocks(tmp_path: Path) -> None:
    from datetime import time as dt_time

    window = SendWindow(start=dt_time(0, 0), end=dt_time(0, 1), days=["Mon"])
    store = _store(tmp_path, daily_send_cap=10, per_domain_daily_cap=10, send_window=window)
    decision = store.can_send("a@x.test", tz_name="UTC")
    if not decision.allowed:
        assert decision.reason == "outside_send_window"


def test_subject_hashed_in_log(tmp_path: Path) -> None:
    import sqlite3

    store = _store(tmp_path)
    store.record_send("a@x.test", subject="confidential plan", source="t")
    with sqlite3.connect(str(tmp_path / "send_log.sqlite")) as conn:
        row = conn.execute("SELECT subject_hash FROM send_log").fetchone()
    assert row is not None
    assert "confidential" not in row[0]
    assert len(row[0]) == 32
