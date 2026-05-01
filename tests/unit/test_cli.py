"""CLI smoke tests."""

from __future__ import annotations

import pytest

from blufire.cli import build_parser


def test_parser_has_top_level_subcommands() -> None:
    parser = build_parser()
    # argparse stashes subparsers in _subparsers; we sniff via parse args
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])


def test_doctor_runs_with_complete_settings(tmp_settings) -> None:
    from blufire.cli import _cmd_doctor

    rc = _cmd_doctor(args=None, settings=tmp_settings)  # type: ignore[arg-type]
    assert rc == 0


def test_doctor_reports_missing_secret(tmp_settings) -> None:
    from blufire.cli import _cmd_doctor

    tmp_settings.secrets.hubspot_api_key = None
    tmp_settings.secrets.anthropic_api_key = None
    rc = _cmd_doctor(args=None, settings=tmp_settings)  # type: ignore[arg-type]
    assert rc == 1


def test_suppress_check_command(tmp_settings, capsys: pytest.CaptureFixture[str]) -> None:
    from blufire.cli import _cmd_suppress

    class _Args:
        subcommand = "check"
        email = "nobody@nowhere.test"
        reason = None
        path = None

    rc = _cmd_suppress(_Args(), tmp_settings)  # type: ignore[arg-type]
    assert rc == 0
    assert "not-suppressed" in capsys.readouterr().out
