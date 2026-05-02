"""Tiny SQLite helper used by the compliance modules. Single-process safe;
adequate for the per-install volume (≤ 100 sends/day per tenant)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with WAL + foreign keys enabled."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_for(path)
    with lock:
        conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def domain_of(email: str) -> str:
    norm = normalize_email(email)
    if "@" not in norm:
        raise ValueError(f"not an email: {email!r}")
    return norm.split("@", 1)[1]
