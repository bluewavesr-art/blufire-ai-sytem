"""Phase 2 tool-registry tests.

Covers: every concrete Tool implements the Protocol; bootstrap() is
idempotent; CapabilityRegistry resolves email_outreach.send to the right
tool names; the email_outreach orchestrator threads tools end-to-end
with the same compliance gating as the Phase 1 module path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from blufire.runtime.bootstrap import (
    CRM_PROVIDERS,
    EMAIL_OUTREACH_BLUEPRINT,
    EMAIL_OUTREACH_CAPABILITY,
    EMAIL_PROVIDERS,
    ProviderNotImplemented,
    bootstrap,
)
from blufire.runtime.capability import CapabilityRegistry, CapabilityUnresolved
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.orchestrators import email_outreach as orchestrator
from blufire.runtime.tool import Tool, ToolRegistry
from blufire.runtime.tools.compliance import (
    BuildFooterOutput,
    CheckSendCapOutput,
    CheckSuppressionOutput,
    RecordConsentOutput,
    RecordSendOutput,
)
from blufire.runtime.tools.crm import ContactRecord, ListContactsOutput, LogEmailOutput
from blufire.runtime.tools.email import SendEmailOutput
from blufire.runtime.tools.llm import DraftOutreachEmailOutput

EXPECTED_TOOLS = sorted(
    [
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "compliance.record_send",
        "compliance.record_consent",
        "compliance.build_footer",
        "crm.list_contacts",
        "crm.log_email",
        "crm.search_contacts",
        "crm.create_contact",
        "crm.list_deals",
        "crm.update_deal",
        "crm.create_deal",
        "crm.create_task",
        "email.send_smtp",
        "prospect.search_people",
        "llm.draft_outreach_email",
        "llm.score_prospect",
        "llm.analyze_pipeline",
    ]
)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_registers_expected_tools(tmp_settings: Any) -> None:
    tools = ToolRegistry()
    caps = CapabilityRegistry(tools)
    bootstrap(tmp_settings, tools, caps)
    assert tools.names() == EXPECTED_TOOLS


def test_bootstrap_is_idempotent(tmp_settings: Any) -> None:
    tools = ToolRegistry()
    caps = CapabilityRegistry(tools)
    bootstrap(tmp_settings, tools, caps)
    # Second call must not raise (existing tools are skipped, capability
    # registration is idempotent because Capability is keyed by name).
    bootstrap(tmp_settings, tools, caps)
    assert tools.names() == EXPECTED_TOOLS


def test_every_tool_satisfies_protocol(tmp_settings: Any) -> None:
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    for name in tools.names():
        tool = tools.get(name)
        assert tool is not None
        assert isinstance(tool, Tool), f"{name} fails Tool protocol"
        # Sanity: schemas exist and pydantic models
        assert hasattr(tool, "input_schema")
        assert hasattr(tool, "output_schema")


def test_capability_resolves_against_populated_registry(tmp_settings: Any) -> None:
    tools = ToolRegistry()
    caps = CapabilityRegistry(tools, strict=True)
    bootstrap(tmp_settings, tools, caps)
    blueprint = caps.resolve(
        {
            "name": "email_outreach",
            "domain": "outreach",
            "description": "x",
            "capabilities": ["email_outreach.send"],
        }
    )
    cap = blueprint.capabilities[0]
    assert cap.name == EMAIL_OUTREACH_CAPABILITY.name
    # Every declared tool must be present in the registry.
    for tool_name in cap.tool_names:
        assert tools.get(tool_name) is not None, tool_name


def test_capability_resolution_strict_raises_when_tool_missing() -> None:
    tools = ToolRegistry()  # empty
    caps = CapabilityRegistry(tools, strict=True)
    caps.register(EMAIL_OUTREACH_CAPABILITY)
    with pytest.raises(CapabilityUnresolved):
        caps.resolve({"name": "email_outreach", "capabilities": ["email_outreach.send"]})


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


def test_hubspot_is_default_crm_provider(tmp_settings: Any) -> None:
    """Default settings → HubSpot tools registered under the generic names."""
    assert tmp_settings.crm.provider == "hubspot"
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    crm_tool = tools.get("crm.list_contacts")
    assert crm_tool is not None
    assert type(crm_tool).__name__ == "HubSpotListContactsTool"


def test_gmail_is_default_email_provider(tmp_settings: Any) -> None:
    assert tmp_settings.email.provider == "gmail"
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    email_tool = tools.get("email.send_smtp")
    assert email_tool is not None
    assert type(email_tool).__name__ == "GmailSendEmailTool"


def test_unimplemented_crm_provider_raises_clear_error(tmp_settings: Any) -> None:
    """A provider declared in the Literal but not yet implemented must
    raise ProviderNotImplemented with a message that names the config key."""
    # Bypass the Literal validator by directly mutating the config object.
    tmp_settings.crm.provider = "jobber"  # type: ignore[assignment]
    tools = ToolRegistry()
    with pytest.raises(ProviderNotImplemented, match="crm.provider='jobber'"):
        bootstrap(tmp_settings, tools, CapabilityRegistry(tools))


def test_unimplemented_email_provider_raises_clear_error(tmp_settings: Any) -> None:
    tmp_settings.email.provider = "mailgun"  # type: ignore[assignment]
    tools = ToolRegistry()
    with pytest.raises(ProviderNotImplemented, match="email.provider='mailgun'"):
        bootstrap(tmp_settings, tools, CapabilityRegistry(tools))


def test_provider_dispatch_tables_are_consistent() -> None:
    """Every key in the dispatch tables must be a string and resolve to a
    real importable module path (we don't import them here — we just sanity-
    check the shape so a typo lands fast)."""
    for table in (CRM_PROVIDERS, EMAIL_PROVIDERS):
        for provider, module_path in table.items():
            assert isinstance(provider, str) and provider
            assert isinstance(module_path, str) and module_path.startswith("blufire.runtime.tools.")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _stub_tool(name: str, output: Any) -> Any:
    """Build a MagicMock that quacks like a Tool and returns ``output``."""
    tool = MagicMock(spec=Tool)
    tool.name = name
    tool.invoke.return_value = output
    return tool


def _ctx(settings: Any) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="email_outreach", run_id="r-1")


def _build_registry(contacts: list[dict[str, Any]], **overrides: Any) -> ToolRegistry:
    """Build a registry pre-populated with stubs for every tool the orchestrator
    needs. Individual stubs can be overridden via kwargs (key = tool name)."""
    defaults = {
        "crm.list_contacts": _stub_tool(
            "crm.list_contacts",
            ListContactsOutput(
                contacts=[
                    ContactRecord(id=str(c["id"]), properties=c.get("properties", {}))
                    for c in contacts
                ]
            ),
        ),
        "compliance.check_suppression": _stub_tool(
            "compliance.check_suppression", CheckSuppressionOutput(suppressed=False)
        ),
        "compliance.check_send_cap": _stub_tool(
            "compliance.check_send_cap", CheckSendCapOutput(allowed=True)
        ),
        "llm.draft_outreach_email": _stub_tool(
            "llm.draft_outreach_email",
            DraftOutreachEmailOutput(subject="Hi", body="Body."),
        ),
        "compliance.build_footer": _stub_tool(
            "compliance.build_footer",
            BuildFooterOutput(
                body_with_footer="Body.\n\n--\nFooter",
                list_unsubscribe="<https://x>",
            ),
        ),
        "compliance.record_consent": _stub_tool(
            "compliance.record_consent",
            RecordConsentOutput(evidence_hash="0" * 64),
        ),
        "email.send_smtp": _stub_tool("email.send_smtp", SendEmailOutput()),
        "compliance.record_send": _stub_tool("compliance.record_send", RecordSendOutput()),
        "crm.log_email": _stub_tool("crm.log_email", LogEmailOutput(logged=True)),
    }
    defaults.update(overrides)
    reg = ToolRegistry()
    for tool in defaults.values():
        reg.register(tool)
    return reg


def test_orchestrator_dry_run_drafts_without_sending(tmp_settings: Any) -> None:
    contacts = [
        {"id": "1", "properties": {"email": "a@example.com", "firstname": "A"}},
        {"id": "2", "properties": {"email": "b@example.com", "firstname": "B"}},
    ]
    reg = _build_registry(contacts)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        EMAIL_OUTREACH_BLUEPRINT,
        campaign_context="test",
        limit=10,
        dry_run=True,
        registry=reg,
    )
    assert counters["drafted_dry_run"] == 2
    assert counters["sent"] == 0
    # send_smtp must NOT be invoked in dry-run mode
    reg.get("email.send_smtp").invoke.assert_not_called()  # type: ignore[union-attr]
    # send-cap check must also be skipped in dry-run
    reg.get("compliance.check_send_cap").invoke.assert_not_called()  # type: ignore[union-attr]


def test_orchestrator_skips_suppressed(tmp_settings: Any) -> None:
    contacts = [{"id": "1", "properties": {"email": "blocked@example.com"}}]
    reg = _build_registry(
        contacts,
        **{
            "compliance.check_suppression": _stub_tool(
                "compliance.check_suppression",
                CheckSuppressionOutput(suppressed=True, reason="dnc"),
            )
        },
    )
    counters = orchestrator.run(
        _ctx(tmp_settings),
        EMAIL_OUTREACH_BLUEPRINT,
        campaign_context="test",
        registry=reg,
    )
    assert counters["skipped_suppressed"] == 1
    assert counters["sent"] == 0
    reg.get("llm.draft_outreach_email").invoke.assert_not_called()  # type: ignore[union-attr]


def test_orchestrator_skips_no_email(tmp_settings: Any) -> None:
    contacts = [{"id": "1", "properties": {"email": "", "firstname": "A"}}]
    reg = _build_registry(contacts)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        EMAIL_OUTREACH_BLUEPRINT,
        campaign_context="test",
        registry=reg,
    )
    assert counters["skipped_no_email"] == 1
    reg.get("compliance.check_suppression").invoke.assert_not_called()  # type: ignore[union-attr]


def test_orchestrator_full_send_path(tmp_settings: Any) -> None:
    contacts = [{"id": "42", "properties": {"email": "good@example.com"}}]
    reg = _build_registry(contacts)
    counters = orchestrator.run(
        _ctx(tmp_settings),
        EMAIL_OUTREACH_BLUEPRINT,
        campaign_context="test",
        registry=reg,
    )
    assert counters["sent"] == 1
    # Verify the send-order pipeline: each gating + side-effect tool fired once.
    for name in (
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "llm.draft_outreach_email",
        "compliance.build_footer",
        "compliance.record_consent",
        "email.send_smtp",
        "compliance.record_send",
        "crm.log_email",
    ):
        reg.get(name).invoke.assert_called_once()  # type: ignore[union-attr]


def test_orchestrator_draft_failure_increments_errors(tmp_settings: Any) -> None:
    contacts = [{"id": "1", "properties": {"email": "good@example.com"}}]
    failing_drafter = _stub_tool("llm.draft_outreach_email", None)
    failing_drafter.invoke.side_effect = RuntimeError("LLM down")
    reg = _build_registry(contacts, **{"llm.draft_outreach_email": failing_drafter})
    counters = orchestrator.run(
        _ctx(tmp_settings),
        EMAIL_OUTREACH_BLUEPRINT,
        campaign_context="test",
        registry=reg,
    )
    assert counters["errors"] == 1
    assert counters["sent"] == 0
    reg.get("email.send_smtp").invoke.assert_not_called()  # type: ignore[union-attr]


def test_orchestrator_raises_when_tool_missing(tmp_settings: Any) -> None:
    reg = ToolRegistry()  # empty
    with pytest.raises(CapabilityUnresolved):
        orchestrator.run(
            _ctx(tmp_settings),
            EMAIL_OUTREACH_BLUEPRINT,
            campaign_context="test",
            registry=reg,
        )
