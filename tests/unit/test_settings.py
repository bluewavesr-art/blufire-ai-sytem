"""Settings load + validate."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from blufire.settings import Settings, load_settings, reset_settings_cache


def test_load_minimal_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    monkeypatch.setenv("GMAIL_USER", "u@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        dedent(f"""
        tenant: {{id: "t", display_name: "T"}}
        paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
        sender:
          name: "N"
          company: "C"
          email: "n@example.com"
          physical_address: "1 Test Way, City, ST 00000"
    """).strip()
    )
    reset_settings_cache()
    settings = load_settings(cfg)
    assert settings.tenant.id == "t"
    assert settings.outreach.daily_send_cap == 50  # default applied


def test_invalid_email_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_API_KEY", "k")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        dedent(f"""
        tenant: {{id: "t", display_name: "T"}}
        paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
        sender:
          name: "N"
          company: "C"
          email: "not-an-email"
          physical_address: "1 Test Way, City, ST 00000"
    """).strip()
    )
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_missing_config_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLUFIRE_CONFIG", raising=False)
    monkeypatch.delenv("BLUFIRE_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    reset_settings_cache()
    with pytest.raises(FileNotFoundError):
        load_settings()


def test_settings_paths_derive_db(tmp_settings: Settings) -> None:
    assert tmp_settings.suppression_db_path.name == "suppression.sqlite"
    assert tmp_settings.send_log_db_path.name == "send_log.sqlite"
    assert tmp_settings.consent_log_db_path.name == "consent_log.sqlite"
