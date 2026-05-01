"""Process-level wiring: populate the default ToolRegistry, register
capabilities, and produce AgentBlueprints. Idempotent: calling
``bootstrap()`` twice is a no-op so test suites can invoke it freely."""

from __future__ import annotations

from blufire.runtime.capability import AgentBlueprint, Capability, CapabilityRegistry
from blufire.runtime.tool import ToolRegistry, default_registry
from blufire.runtime.tools.compliance import (
    BuildFooterTool,
    CheckSendCapTool,
    CheckSuppressionTool,
    RecordConsentTool,
    RecordSendTool,
)
from blufire.runtime.tools.crm import ListContactsTool, LogEmailTool
from blufire.runtime.tools.email import SendEmailTool
from blufire.runtime.tools.llm import DraftOutreachEmailTool

EMAIL_OUTREACH_CAPABILITY = Capability(
    name="email_outreach.send",
    tool_names=(
        "crm.list_contacts",
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "llm.draft_outreach_email",
        "compliance.build_footer",
        "compliance.record_consent",
        "email.send_smtp",
        "compliance.record_send",
        "crm.log_email",
    ),
    required=True,
)

EMAIL_OUTREACH_BLUEPRINT = AgentBlueprint(
    name="email_outreach",
    domain="outreach",
    description="Drafts and sends compliant cold outreach emails to HubSpot contacts.",
    capabilities=(EMAIL_OUTREACH_CAPABILITY,),
)


def _register_if_missing(registry: ToolRegistry, tool: object) -> None:
    name: str = getattr(tool, "name")  # noqa: B009 — Protocol attr
    if registry.get(name) is None:
        registry.register(tool)  # type: ignore[arg-type]


def bootstrap(
    tools: ToolRegistry | None = None,
    capabilities: CapabilityRegistry | None = None,
) -> tuple[ToolRegistry, CapabilityRegistry]:
    """Register all built-in Tools and Capabilities. Idempotent."""
    tools = tools or default_registry
    capabilities = capabilities or CapabilityRegistry(tools)

    for tool_cls in (
        CheckSuppressionTool,
        CheckSendCapTool,
        RecordSendTool,
        RecordConsentTool,
        BuildFooterTool,
        ListContactsTool,
        LogEmailTool,
        SendEmailTool,
        DraftOutreachEmailTool,
    ):
        _register_if_missing(tools, tool_cls())

    capabilities.register(EMAIL_OUTREACH_CAPABILITY)

    return tools, capabilities
