from __future__ import annotations

import json

import pytest

from blufire.logging_setup import configure, get_logger, new_run_id


def test_configure_writes_json_line(tmp_settings, capsys: pytest.CaptureFixture[str]) -> None:
    configure(tmp_settings)
    log = get_logger("test").bind(tenant_id=tmp_settings.tenant.id, run_id="r1")
    log.info("event_x", foo=1)
    captured = capsys.readouterr().out
    assert captured.strip(), "expected at least one log line"
    line = captured.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "event_x"
    assert payload["foo"] == 1
    assert payload["tenant_id"] == tmp_settings.tenant.id


def test_configure_creates_file_handler(tmp_settings) -> None:
    configure(tmp_settings)
    expected = tmp_settings.paths.log_dir / "blufire.log"
    log = get_logger("test").bind(tenant_id=tmp_settings.tenant.id)
    log.info("file_handler_smoke")
    assert expected.exists()


def test_new_run_id_is_uuid_like() -> None:
    rid = new_run_id()
    assert len(rid) == 36
    assert rid.count("-") == 4
