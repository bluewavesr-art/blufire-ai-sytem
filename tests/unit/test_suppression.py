from __future__ import annotations

from pathlib import Path

from blufire.compliance.suppression import SuppressionList


def test_add_and_check(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    s = SuppressionList(db, "tenant1")
    assert s.is_suppressed("Alice@Example.com") is False
    s.add("alice@example.com", reason="manual", source="test")
    assert s.is_suppressed("Alice@Example.com") is True


def test_domain_block_implies_email(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    s = SuppressionList(db, "tenant1")
    s.add_domain("blocked.test", reason="spam")
    assert s.is_suppressed("anyone@blocked.test") is True
    assert s.is_suppressed("anyone@allowed.test") is False


def test_csv_import(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    csv.write_text("email\na@x.test\nB@x.test\n")
    s = SuppressionList(tmp_path / "s.sqlite", "tenant1")
    added = s.import_csv(csv)
    assert added == 2
    assert s.is_suppressed("a@x.test")
    assert s.is_suppressed("b@x.test")


def test_idempotent_add(tmp_path: Path) -> None:
    s = SuppressionList(tmp_path / "s.sqlite", "tenant1")
    s.add("dup@x.test", reason="r1", source="src1")
    s.add("dup@x.test", reason="r2", source="src2")
    assert s.is_suppressed("dup@x.test")


def test_malformed_email_blocked(tmp_path: Path) -> None:
    s = SuppressionList(tmp_path / "s.sqlite", "tenant1")
    assert s.is_suppressed("not-an-email") is True
