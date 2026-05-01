"""Tests for the Google Sheets CRM + email-draft providers.

We don't hit the real Google Sheets API — every test patches
``GSheetsClient`` with an in-memory fake that records appends and
returns canned ``list_rows`` results. The point is to exercise the
provider's mapping logic (dedup, append shape, soft no-ops on deals/
tasks) and the bootstrap dispatch wiring.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from blufire.runtime.bootstrap import (
    CRM_PROVIDERS,
    EMAIL_DRAFT_PROVIDERS,
    bootstrap,
)
from blufire.runtime.capability import CapabilityRegistry
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools.crm import (
    CreateContactInput,
    CreateDealInput,
    CreateTaskInput,
    ListContactsInput,
    ListDealsInput,
    LogEmailInput,
    SearchContactsInput,
    UpdateDealInput,
)
from blufire.runtime.tools.crm_gsheets import (
    GSheetsCreateContactTool,
    GSheetsCreateDealTool,
    GSheetsCreateTaskTool,
    GSheetsListContactsTool,
    GSheetsListDealsTool,
    GSheetsLogEmailTool,
    GSheetsSearchContactsTool,
    GSheetsUpdateDealTool,
)
from blufire.runtime.tools.email import CreateDraftInput
from blufire.runtime.tools.email_gsheets import GSheetsCreateDraftTool


class _FakeGSheets:
    """In-memory stand-in for GSheetsClient. Keyed by (sheet_url, worksheet)."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = rows or []
        self.appended: list[tuple[str, str, list[Any]]] = []

    def append_row(self, sheet_url: str, worksheet: str, row: list[Any]) -> None:
        self.appended.append((sheet_url, worksheet, row))

    def list_rows(self, sheet_url: str, worksheet: str, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)


def _ctx(settings: Any) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="t", run_id="r")


@pytest.fixture
def gsheets_settings(tmp_settings: Any) -> Any:
    """Configure the test tmp_settings to use gsheets and a stub URL."""
    tmp_settings.crm.provider = "gsheets"  # type: ignore[assignment]
    tmp_settings.email.draft_provider = "gsheets"  # type: ignore[assignment]
    tmp_settings.gsheets.spreadsheet_url = "https://docs.google.com/spreadsheets/d/abc"  # type: ignore[assignment]
    tmp_settings.gsheets.leads_worksheet = "Leads"
    tmp_settings.gsheets.drafts_worksheet = "Drafts"
    return tmp_settings


# ---------------------------------------------------------------------------
# crm_gsheets tools
# ---------------------------------------------------------------------------


def test_search_contacts_finds_existing_email(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(
        rows=[
            {"email": "alice@example.com", "first_name": "Alice"},
            {"email": "bob@example.com", "first_name": "Bob"},
        ]
    )
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsSearchContactsTool().invoke(
            _ctx(gsheets_settings), SearchContactsInput(email="bob@example.com")
        )
    assert len(out.contacts) == 1
    assert out.contacts[0].properties["first_name"] == "Bob"


def test_search_contacts_is_case_insensitive(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(rows=[{"email": "Alice@Example.COM"}])
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsSearchContactsTool().invoke(
            _ctx(gsheets_settings), SearchContactsInput(email="alice@example.com")
        )
    assert len(out.contacts) == 1


def test_search_contacts_returns_empty_when_not_found(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(rows=[{"email": "alice@example.com"}])
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsSearchContactsTool().invoke(
            _ctx(gsheets_settings), SearchContactsInput(email="nobody@example.com")
        )
    assert out.contacts == []


def test_create_contact_appends_row_when_email_is_new(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(rows=[])
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsCreateContactTool().invoke(
            _ctx(gsheets_settings),
            CreateContactInput(
                properties={
                    "email": "new@example.com",
                    "first_name": "New",
                    "last_name": "Lead",
                    "company": "ACME",
                }
            ),
        )
    assert out.contact_id == "new@example.com"
    assert out.already_existed is False
    assert len(fake.appended) == 1
    sheet_url, worksheet, row = fake.appended[0]
    assert worksheet == "Leads"
    # Row order matches LEADS_COLUMNS — email is column 0.
    assert row[0] == "new@example.com"
    assert row[1] == "New"
    # created_at timestamp is the last column; sanity-check it exists.
    assert row[-1] != ""


def test_create_contact_dedup_via_email_match(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(rows=[{"email": "dup@example.com"}])
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsCreateContactTool().invoke(
            _ctx(gsheets_settings),
            CreateContactInput(properties={"email": "dup@example.com"}),
        )
    assert out.already_existed is True
    assert out.contact_id is None
    assert fake.appended == []  # critical: no double-append


def test_list_contacts_respects_limit(gsheets_settings: Any) -> None:
    fake = _FakeGSheets(rows=[{"email": f"u{i}@x.test"} for i in range(20)])
    with patch("blufire.runtime.tools.crm_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsListContactsTool().invoke(_ctx(gsheets_settings), ListContactsInput(limit=5))
    assert len(out.contacts) == 5


def test_log_email_is_soft_noop(gsheets_settings: Any) -> None:
    out = GSheetsLogEmailTool().invoke(
        _ctx(gsheets_settings), LogEmailInput(contact_id="x", subject="s", body="b")
    )
    assert out.logged is False
    assert out.error == "not_supported_by_provider"


def test_deals_and_tasks_are_soft_noops(gsheets_settings: Any) -> None:
    """The orchestrators for crm_pipeline + lead_gen need these to degrade
    gracefully rather than raising — a sheets-only tenant doesn't have deals
    or tasks but should still be runnable."""
    list_out = GSheetsListDealsTool().invoke(_ctx(gsheets_settings), ListDealsInput())
    assert list_out.deals == []

    update_out = GSheetsUpdateDealTool().invoke(
        _ctx(gsheets_settings), UpdateDealInput(deal_id="x", properties={})
    )
    assert update_out.updated is False
    assert update_out.error == "not_supported_by_provider"

    create_out = GSheetsCreateDealTool().invoke(
        _ctx(gsheets_settings), CreateDealInput(dealname="d", stage="s")
    )
    assert create_out.deal_id is None

    task_out = GSheetsCreateTaskTool().invoke(_ctx(gsheets_settings), CreateTaskInput(title="t"))
    assert task_out.created is False


# ---------------------------------------------------------------------------
# email_gsheets
# ---------------------------------------------------------------------------


def test_create_draft_appends_to_drafts_worksheet(gsheets_settings: Any) -> None:
    fake = _FakeGSheets()
    with patch("blufire.runtime.tools.email_gsheets.GSheetsClient", return_value=fake):
        out = GSheetsCreateDraftTool().invoke(
            _ctx(gsheets_settings),
            CreateDraftInput(
                to="lead@example.com",
                subject="Storm-damage assessment",
                body="Hello — body here.",
                list_unsubscribe="<https://x>",
            ),
        )
    assert out.created is True
    assert len(fake.appended) == 1
    _, worksheet, row = fake.appended[0]
    assert worksheet == "Drafts"
    # DRAFTS_COLUMNS = (created_at, to, subject, body, list_unsubscribe, status)
    assert row[1] == "lead@example.com"
    assert row[2] == "Storm-damage assessment"
    assert row[3] == "Hello — body here."
    assert row[4] == "<https://x>"
    assert row[5] == "draft"


def test_create_draft_returns_error_when_no_spreadsheet_url(tmp_settings: Any) -> None:
    # Ensure spreadsheet_url is None — that's the default.
    assert tmp_settings.gsheets.spreadsheet_url is None
    out = GSheetsCreateDraftTool().invoke(
        _ctx(tmp_settings),
        CreateDraftInput(to="x@y.test", subject="s", body="b"),
    )
    assert out.created is False
    assert out.error == "spreadsheet_url_not_configured"


# ---------------------------------------------------------------------------
# Bootstrap dispatch wiring
# ---------------------------------------------------------------------------


def test_gsheets_is_registered_in_dispatch_tables() -> None:
    assert "gsheets" in CRM_PROVIDERS
    assert "gsheets" in EMAIL_DRAFT_PROVIDERS
    assert CRM_PROVIDERS["gsheets"] == "blufire.runtime.tools.crm_gsheets"
    assert EMAIL_DRAFT_PROVIDERS["gsheets"] == "blufire.runtime.tools.email_gsheets"


def test_bootstrap_with_gsheets_provider_registers_correct_impls(gsheets_settings: Any) -> None:
    tools = ToolRegistry()
    bootstrap(gsheets_settings, tools, CapabilityRegistry(tools))
    crm_search = tools.get("crm.search_contacts")
    draft_tool = tools.get("email.create_draft")
    assert crm_search is not None
    assert draft_tool is not None
    assert type(crm_search).__name__ == "GSheetsSearchContactsTool"
    assert type(draft_tool).__name__ == "GSheetsCreateDraftTool"
