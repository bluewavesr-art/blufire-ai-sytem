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


def test_invalid_timezone_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
tenant: {{id: "t", display_name: "T", timezone: "Mars/Olympus"}}
paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
sender:
  name: "N"
  company: "C"
  email: "n@example.com"
  physical_address: "1 Test Way, City, ST 00000"
""".strip()
    )
    with pytest.raises(ValueError, match="unknown timezone"):
        load_settings(cfg)


def test_prospects_without_webhook_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
tenant: {{id: "t", display_name: "T"}}
paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
sender:
  name: "N"
  company: "C"
  email: "n@example.com"
  physical_address: "1 Test Way, City, ST 00000"
prospect_searches:
  - name: "test search"
    person_titles: ["CEO"]
    per_page: 10
""".strip()
    )
    with pytest.raises(ValueError, match="webhook"):
        load_settings(cfg)


def test_prospects_with_gsheets_draft_provider_skips_webhook_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gsheets draft sink doesn't need a webhook URL — validator must
    only fire for draft_provider='make_webhook'."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
tenant: {{id: "t", display_name: "T"}}
paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
sender:
  name: "N"
  company: "C"
  email: "n@example.com"
  physical_address: "1 Test Way, City, ST 00000"
email:
  draft_provider: "gsheets"
gsheets:
  spreadsheet_url: "https://docs.google.com/spreadsheets/d/x/edit"
prospect_searches:
  - name: "test"
    per_page: 5
""".strip()
    )
    settings = load_settings(cfg)
    assert settings.email.draft_provider == "gsheets"
    assert settings.outreach.webhook.gmail_draft_url is None


def test_prospects_with_webhook_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
tenant: {{id: "t", display_name: "T"}}
paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
sender:
  name: "N"
  company: "C"
  email: "n@example.com"
  physical_address: "1 Test Way, City, ST 00000"
prospect_searches:
  - name: "test"
    per_page: 5
outreach:
  webhook:
    gmail_draft_url: "https://hook.example.com/x"
""".strip()
    )
    settings = load_settings(cfg)
    assert len(settings.prospect_searches) == 1
    assert str(settings.outreach.webhook.gmail_draft_url) == "https://hook.example.com/x"


def test_tenant_env_file_loaded_from_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Secrets in <config_stem>.env are picked up when load_settings is given
    the explicit config path — the installer writes backyard-builders.env next
    to backyard-builders.yaml and the loader must find it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BLUFIRE_CONFIG", raising=False)

    cfg = tmp_path / "backyard-builders.yaml"
    env = tmp_path / "backyard-builders.env"
    cfg.write_text(
        f"""
tenant: {{id: "t", display_name: "T"}}
paths: {{data_dir: "{tmp_path}/d", log_dir: "{tmp_path}/l"}}
sender:
  name: "N"
  company: "C"
  email: "n@example.com"
  physical_address: "1 Test Way, City, ST 00000"
""".strip()
    )
    env.write_text("ANTHROPIC_API_KEY=sk-test-key\n")

    settings = load_settings(cfg)
    assert settings.secrets.anthropic_api_key is not None
    assert settings.secrets.anthropic_api_key.get_secret_value() == "sk-test-key"
