"""Tests for the Phase 2 daily_lead_gen orchestrator + email.create_draft contract."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from blufire.runtime.bootstrap import (
    DAILY_LEADGEN_BLUEPRINT,
    EMAIL_DRAFT_PROVIDERS,
    ProviderNotImplemented,
    bootstrap,
)
from blufire.runtime.capability import CapabilityRegistry, CapabilityUnresolved
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.orchestrators import daily_lead_gen as orchestrator
from blufire.runtime.tool import Tool, ToolRegistry
from blufire.runtime.tools.compliance import (
    BuildFooterOutput,
    CheckSendCapOutput,
    CheckSuppressionOutput,
    RecordConsentOutput,
)
from blufire.runtime.tools.crm import (
    AppendCallLeadOutput,
    ContactRecord,
    CreateContactOutput,
    SearchContactsOutput,
)
from blufire.runtime.tools.email import CreateDraftOutput
from blufire.runtime.tools.enrich import FindEmailOutput
from blufire.runtime.tools.llm import DraftOutreachFromProspectOutput
from blufire.runtime.tools.prospect import PersonRecord, SearchPeopleOutput
from blufire.settings import ProspectSearch


def _stub(name: str, output: Any) -> Any:
    tool = MagicMock(spec=Tool)
    tool.name = name
    tool.invoke.return_value = output
    return tool


def _ctx(settings: Any) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="daily_lead_gen", run_id="r-1")


def _registry(
    people: list[dict[str, Any]],
    *,
    existing_emails: set[str] | None = None,
    suppressed_emails: set[str] | None = None,
    capped_emails: set[str] | None = None,
    draft_succeeds: bool = True,
) -> ToolRegistry:
    """Build a registry of stub tools sized to a single ProspectSearch's worth
    of people. Per-call branching for dedup / suppression / cap / draft is
    encoded via side-effect functions so tests can vary one branch at a time."""
    existing_emails = existing_emails or set()
    suppressed_emails = suppressed_emails or set()
    capped_emails = capped_emails or set()

    person_records = [
        PersonRecord(
            email=p.get("email"),
            first_name=p.get("first_name"),
            last_name=p.get("last_name"),
            title=p.get("title"),
            company=(p.get("organization") or {}).get("name"),
            raw=p,
        )
        for p in people
    ]
    reg = ToolRegistry()
    reg.register(_stub("prospect.search_people", SearchPeopleOutput(people=person_records)))

    search_tool = MagicMock(spec=Tool)
    search_tool.name = "crm.search_contacts"

    def search_side_effect(_ctx: Any, payload: Any) -> SearchContactsOutput:
        if payload.email in existing_emails:
            return SearchContactsOutput(
                contacts=[ContactRecord(id=f"existing-{payload.email}", properties={})]
            )
        return SearchContactsOutput(contacts=[])

    search_tool.invoke.side_effect = search_side_effect
    reg.register(search_tool)

    sup_tool = MagicMock(spec=Tool)
    sup_tool.name = "compliance.check_suppression"

    def sup_side_effect(_ctx: Any, payload: Any) -> CheckSuppressionOutput:
        return CheckSuppressionOutput(
            suppressed=payload.email in suppressed_emails,
            reason="dnc" if payload.email in suppressed_emails else None,
        )

    sup_tool.invoke.side_effect = sup_side_effect
    reg.register(sup_tool)

    cap_tool = MagicMock(spec=Tool)
    cap_tool.name = "compliance.check_send_cap"

    def cap_side_effect(_ctx: Any, payload: Any) -> CheckSendCapOutput:
        capped = payload.email in capped_emails
        return CheckSendCapOutput(
            allowed=not capped, reason="daily_cap_reached" if capped else None
        )

    cap_tool.invoke.side_effect = cap_side_effect
    reg.register(cap_tool)

    reg.register(_stub("crm.create_contact", CreateContactOutput(contact_id="new-id")))
    reg.register(
        _stub(
            "llm.draft_outreach_email_from_prospect",
            DraftOutreachFromProspectOutput(subject="Hi", body="Body."),
        )
    )
    reg.register(
        _stub(
            "compliance.build_footer",
            BuildFooterOutput(body_with_footer="Body.\n--\nFooter", list_unsubscribe=None),
        )
    )
    reg.register(_stub("compliance.record_consent", RecordConsentOutput(evidence_hash="0" * 64)))
    reg.register(
        _stub(
            "email.create_draft",
            CreateDraftOutput(created=draft_succeeds, error=None if draft_succeeds else "http_500"),
        )
    )
    # Phase 3 additions: enrichment + call-list sink. Defaults are no-ops
    # for the existing tests (every test person has an email already).
    reg.register(
        _stub("enrich.find_email", FindEmailOutput(email=None, confidence="none", source=""))
    )
    reg.register(_stub("crm.append_call_lead", AppendCallLeadOutput(appended=True)))
    return reg


def _search(per_page: int = 10) -> ProspectSearch:
    return ProspectSearch(name="t", person_titles=["CEO"], per_page=per_page)


# ---------------------------------------------------------------------------
# Filter pipeline
# ---------------------------------------------------------------------------


def test_full_path_drafts_one_per_survivor(tmp_settings: Any) -> None:
    people = [
        {"first_name": "A", "last_name": "X", "email": "a@x.test", "title": "CEO"},
        {"first_name": "B", "last_name": "Y", "email": "b@y.test", "title": "CEO"},
    ]
    reg = _registry(people)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["fetched"] == 2
    assert counters["drafted"] == 2
    assert counters["errors"] == 0
    assert counters["skipped_unreachable"] == 0
    assert counters["routed_to_call_list"] == 0
    assert counters["skipped_existing"] == 0
    assert counters["skipped_suppressed"] == 0
    assert counters["skipped_capped"] == 0
    assert reg.get("email.create_draft").invoke.call_count == 2  # type: ignore[union-attr]


def test_intra_run_dedup_avoids_double_drafting(tmp_settings: Any) -> None:
    """The same email appearing in two searches must only be drafted once."""
    people = [
        {"first_name": "A", "email": "dup@x.test"},
        {"first_name": "A again", "email": "dup@x.test"},
    ]
    reg = _registry(people)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["fetched"] == 2  # both fetched from upstream
    assert counters["drafted"] == 1  # but only one drafted (dedup'd)


def test_skips_existing_crm_contact_before_drafting(tmp_settings: Any) -> None:
    people = [{"first_name": "Old", "email": "in-crm@x.test"}]
    reg = _registry(people, existing_emails={"in-crm@x.test"})
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["skipped_existing"] == 1
    assert counters["drafted"] == 0
    # Drafter must NOT be invoked — it costs Claude tokens.
    assert reg.get("llm.draft_outreach_email_from_prospect").invoke.call_count == 0  # type: ignore[union-attr]


def test_skips_suppressed_before_drafting(tmp_settings: Any) -> None:
    people = [{"first_name": "Blocked", "email": "blocked@x.test"}]
    reg = _registry(people, suppressed_emails={"blocked@x.test"})
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["skipped_suppressed"] == 1
    assert counters["drafted"] == 0
    assert reg.get("llm.draft_outreach_email_from_prospect").invoke.call_count == 0  # type: ignore[union-attr]


def test_skips_capped_before_drafting(tmp_settings: Any) -> None:
    people = [{"first_name": "Capped", "email": "over@x.test"}]
    reg = _registry(people, capped_emails={"over@x.test"})
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["skipped_capped"] == 1
    assert counters["drafted"] == 0


def test_no_email_no_phone_is_unreachable(tmp_settings: Any) -> None:
    """Truly unreachable prospects (no email, no phone, no website) are
    counted as ``skipped_unreachable`` and silently dropped."""
    people = [
        {"first_name": "Nameless", "email": None},
        {"first_name": "Has", "email": "ok@x.test"},
    ]
    reg = _registry(people)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["skipped_unreachable"] == 1
    assert counters["drafted"] == 1


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def test_draft_failure_does_not_abort_remaining_prospects(tmp_settings: Any) -> None:
    """One LLM failure mid-run must increment errors and continue."""
    people = [
        {"first_name": "A", "email": "a@x.test"},
        {"first_name": "B", "email": "b@x.test"},
    ]
    reg = _registry(people)
    failing_drafter = MagicMock(spec=Tool)
    failing_drafter.name = "llm.draft_outreach_email_from_prospect"
    failing_drafter.invoke.side_effect = [
        RuntimeError("LLM down"),
        DraftOutreachFromProspectOutput(subject="ok", body="ok"),
    ]
    # Replace the drafter in the registry
    reg2 = ToolRegistry()
    for name in (
        "prospect.search_people",
        "enrich.find_email",
        "crm.search_contacts",
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "crm.create_contact",
        "compliance.build_footer",
        "compliance.record_consent",
        "email.create_draft",
        "crm.append_call_lead",
    ):
        reg2.register(reg.get(name))  # type: ignore[arg-type]
    reg2.register(failing_drafter)

    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg2,
    )
    assert counters["errors"] == 1
    assert counters["drafted"] == 1


def test_webhook_failure_increments_errors_but_continues(tmp_settings: Any) -> None:
    people = [{"first_name": "A", "email": "a@x.test"}]
    reg = _registry(people, draft_succeeds=False)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["errors"] == 1
    assert counters["drafted"] == 0


def test_raises_when_required_tool_missing(tmp_settings: Any) -> None:
    with pytest.raises(CapabilityUnresolved):
        orchestrator.run(
            _ctx(tmp_settings),
            DAILY_LEADGEN_BLUEPRINT,
            searches=[_search()],
            sleep_between_searches=0,
            registry=ToolRegistry(),
        )


# ---------------------------------------------------------------------------
# Bifurcation: enrichment + call-list routing for Places-style providers
# ---------------------------------------------------------------------------


def _places_registry(
    people: list[dict[str, Any]],
    *,
    enrichment_email: str | None = None,
    enrichment_confidence: str = "high",
    call_list_succeeds: bool = True,
) -> ToolRegistry:
    """A registry whose prospects come in WITHOUT email (Places-style).
    The enrichment stub returns ``enrichment_email`` for any website it's
    asked about — set to ``None`` to simulate an unsuccessful scrape."""
    person_records = [
        PersonRecord(
            email=p.get("email"),
            company=p.get("company"),
            phone=p.get("phone"),
            address=p.get("address"),
            city=p.get("city"),
            state=p.get("state"),
            website=p.get("website"),
            raw=p,
        )
        for p in people
    ]
    reg = ToolRegistry()
    reg.register(_stub("prospect.search_people", SearchPeopleOutput(people=person_records)))
    reg.register(
        _stub(
            "enrich.find_email",
            FindEmailOutput(email=enrichment_email, confidence=enrichment_confidence, source="t"),
        )
    )
    reg.register(_stub("crm.search_contacts", SearchContactsOutput(contacts=[])))
    reg.register(_stub("compliance.check_suppression", CheckSuppressionOutput(suppressed=False)))
    reg.register(_stub("compliance.check_send_cap", CheckSendCapOutput(allowed=True)))
    reg.register(_stub("crm.create_contact", CreateContactOutput(contact_id="c-1")))
    reg.register(
        _stub(
            "llm.draft_outreach_email_from_prospect",
            DraftOutreachFromProspectOutput(subject="S", body="B"),
        )
    )
    reg.register(
        _stub(
            "compliance.build_footer",
            BuildFooterOutput(body_with_footer="B + footer", list_unsubscribe=None),
        )
    )
    reg.register(_stub("compliance.record_consent", RecordConsentOutput(evidence_hash="0" * 64)))
    reg.register(_stub("email.create_draft", CreateDraftOutput(created=True)))
    reg.register(_stub("crm.append_call_lead", AppendCallLeadOutput(appended=call_list_succeeds)))
    return reg


def test_enrichment_promotes_no_email_lead_to_draft_path(tmp_settings: Any) -> None:
    people = [
        {
            "company": "ACME Property Mgmt",
            "phone": "555-1234",
            "website": "https://acme.test",
        }
    ]
    reg = _places_registry(people, enrichment_email="info@acme.test")
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["enriched_email_found"] == 1
    assert counters["drafted"] == 1
    assert counters["routed_to_call_list"] == 0
    # Critical: enrichment was attempted (Places lead had no email).
    reg.get("enrich.find_email").invoke.assert_called_once()  # type: ignore[union-attr]
    reg.get("crm.append_call_lead").invoke.assert_not_called()  # type: ignore[union-attr]


def test_failed_enrichment_routes_to_call_list_when_phone_present(
    tmp_settings: Any,
) -> None:
    people = [
        {
            "company": "ACME Property Mgmt",
            "phone": "555-1234",
            "address": "100 Main St",
            "city": "Fort Worth",
            "state": "TX",
            "website": "https://acme.test",
        }
    ]
    reg = _places_registry(people, enrichment_email=None)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["routed_to_call_list"] == 1
    assert counters["drafted"] == 0
    assert counters["enriched_email_found"] == 0
    # Critical: drafter was NOT invoked (no email).
    reg.get("llm.draft_outreach_email_from_prospect").invoke.assert_not_called()  # type: ignore[union-attr]
    # Critical: call-list sink was invoked with the phone number.
    call_args = reg.get("crm.append_call_lead").invoke.call_args  # type: ignore[union-attr]
    payload = call_args.args[1]
    assert payload.phone == "555-1234"
    assert payload.company == "ACME Property Mgmt"
    assert payload.city == "Fort Worth"
    assert payload.talking_points  # non-empty


def test_no_email_no_phone_no_website_is_skipped(tmp_settings: Any) -> None:
    """No way to reach this prospect — drop it without writing anywhere."""
    people = [{"company": "Mystery Co"}]
    reg = _places_registry(people, enrichment_email=None)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["skipped_unreachable"] == 1
    reg.get("crm.append_call_lead").invoke.assert_not_called()  # type: ignore[union-attr]
    reg.get("email.create_draft").invoke.assert_not_called()  # type: ignore[union-attr]


def test_phone_only_no_website_routes_to_call_list_without_enrichment(
    tmp_settings: Any,
) -> None:
    """If there's no website to scrape, we skip enrichment but still
    route to the call list as long as we have a phone."""
    people = [{"company": "Phone Only Co", "phone": "555-9999"}]
    reg = _places_registry(people, enrichment_email=None)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg,
    )
    assert counters["routed_to_call_list"] == 1
    # Enrichment skipped because website is missing.
    reg.get("enrich.find_email").invoke.assert_not_called()  # type: ignore[union-attr]


def test_enrichment_failure_falls_back_to_call_list(tmp_settings: Any) -> None:
    """If enrich.find_email raises, increment errors implicitly via the
    no-email path → call-list (lead isn't lost just because the scrape
    crashed)."""
    people = [
        {
            "company": "Crashy Co",
            "phone": "555-0000",
            "website": "https://crashy.test",
        }
    ]
    reg = _places_registry(people, enrichment_email=None)
    crashing_enricher = MagicMock(spec=Tool)
    crashing_enricher.name = "enrich.find_email"
    crashing_enricher.invoke.side_effect = RuntimeError("scrape blew up")
    # Replace the enricher.
    reg2 = ToolRegistry()
    for name in (
        "prospect.search_people",
        "crm.search_contacts",
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "crm.create_contact",
        "llm.draft_outreach_email_from_prospect",
        "compliance.build_footer",
        "compliance.record_consent",
        "email.create_draft",
        "crm.append_call_lead",
    ):
        reg2.register(reg.get(name))  # type: ignore[arg-type]
    reg2.register(crashing_enricher)

    counters = orchestrator.run(
        _ctx(tmp_settings),
        DAILY_LEADGEN_BLUEPRINT,
        searches=[_search()],
        sleep_between_searches=0,
        registry=reg2,
    )
    assert counters["routed_to_call_list"] == 1
    assert counters["enriched_email_found"] == 0


# ---------------------------------------------------------------------------
# email.draft_provider dispatch
# ---------------------------------------------------------------------------


def test_make_webhook_is_default_draft_provider(tmp_settings: Any) -> None:
    assert tmp_settings.email.draft_provider == "make_webhook"
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    tool = tools.get("email.create_draft")
    assert tool is not None
    assert type(tool).__name__ == "MakeWebhookCreateDraftTool"


def test_unimplemented_draft_provider_raises(tmp_settings: Any) -> None:
    tmp_settings.email.draft_provider = "gmail_api"  # type: ignore[assignment]
    tools = ToolRegistry()
    with pytest.raises(ProviderNotImplemented, match="email.draft_provider='gmail_api'"):
        bootstrap(tmp_settings, tools, CapabilityRegistry(tools))


def test_email_draft_dispatch_table_only_contains_runtime_paths() -> None:
    for provider, module_path in EMAIL_DRAFT_PROVIDERS.items():
        assert isinstance(provider, str) and provider
        assert module_path.startswith("blufire.runtime.tools.")
