"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from blufire.settings import Settings, reset_settings_cache


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate the four required secrets so Settings validates."""
    monkeypatch.setenv("HUBSPOT_API_KEY", "hs-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-test-key")
    monkeypatch.setenv("APOLLO_API_KEY", "apollo-test-key")
    monkeypatch.setenv("GMAIL_USER", "test@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-password")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://unsub.example.com")
    monkeypatch.setenv("MAKE_DRAFT_WEBHOOK_URL", "https://hook.example.com/draft")


@pytest.fixture
def tmp_settings(tmp_path: Path, fake_env: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Build a Settings object backed by tmp_path. Use this everywhere a Settings is needed."""
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    config_path.write_text(
        dedent(
            f"""
            tenant:
              id: "test-tenant"
              display_name: "Test"
              timezone: "UTC"
            paths:
              data_dir: "{data_dir}"
              log_dir: "{log_dir}"
            sender:
              name: "Test Sender"
              company: "Test Co"
              email: "sender@example.com"
              physical_address: "1 Test Way, Test City, TS 00000"
            outreach:
              daily_send_cap: 50
              per_domain_daily_cap: 5
              webhook:
                gmail_draft_url: "${{MAKE_DRAFT_WEBHOOK_URL}}"
            compliance:
              unsubscribe_base_url: "${{UNSUBSCRIBE_BASE_URL}}"
              legal_basis: "legitimate_interest"
              jurisdiction: ["US"]
            logging:
              level: "INFO"
              format: "json"
            """
        ).strip()
    )
    monkeypatch.setenv("BLUFIRE_CONFIG", str(config_path))
    reset_settings_cache()
    from blufire.settings import load_settings

    return load_settings(config_path)


@pytest.fixture(autouse=True)
def _no_real_log_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep test log writes inside tmp_path."""
    monkeypatch.setenv("BLUFIRE_HOME", str(tmp_path))


@pytest.fixture
def webhook_responses() -> Any:
    import responses as resp_lib

    with resp_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps
