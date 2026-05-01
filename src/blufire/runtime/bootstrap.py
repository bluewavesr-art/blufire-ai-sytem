"""Process-level wiring: populate the default ToolRegistry, register
capabilities, and produce AgentBlueprints. Idempotent — calling
``bootstrap()`` twice is a no-op so test suites can invoke it freely.

Provider dispatch
-----------------

Tool *contracts* (``crm.list_contacts``, ``email.send_smtp``, …) are
backend-agnostic. The orchestrator only knows the contract name. Which
concrete implementation backs that name is driven by
``settings.crm.provider`` and ``settings.email.provider``.

Each provider module exposes a single ``register(tools: ToolRegistry)``
function that knows which tool names it backs. Bootstrap looks up the
configured providers in the dispatch tables below, imports them lazily,
and calls ``register()``.

Adding a new provider — say AccuLynx — looks like:

    1. Implement ``runtime/tools/crm_acculynx.py`` with the relevant
       ``BaseTool`` subclasses and a module-level ``register(tools)``.
    2. Add ``"acculynx": "blufire.runtime.tools.crm_acculynx"`` to
       ``CRM_PROVIDERS`` below.
    3. Add the literal to ``CrmProvider`` in ``settings.py``.

A provider that backs *both* a CRM and an email sender (GHL is the
canonical example) lives in two modules, one per namespace
(``crm_ghl.py``, ``email_ghl.py``). They register independently;
operators opt into either or both via settings.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from blufire.runtime.capability import AgentBlueprint, Capability, CapabilityRegistry
from blufire.runtime.tool import ToolRegistry, default_registry
from blufire.runtime.tools.compliance import (
    BuildFooterTool,
    CheckSendCapTool,
    CheckSuppressionTool,
    RecordConsentTool,
    RecordSendTool,
)
from blufire.runtime.tools.llm import (
    AnalyzePipelineTool,
    DraftOutreachEmailTool,
    DraftOutreachFromProspectTool,
    ScoreProspectTool,
)
from blufire.settings import Settings, get_settings

# Provider dispatch tables. The values are dotted module paths whose
# top-level ``register(tools)`` function will be called for any tenant
# that selects that provider.
CRM_PROVIDERS: dict[str, str] = {
    "hubspot": "blufire.runtime.tools.crm_hubspot",
    # "jobber":      "blufire.runtime.tools.crm_jobber",
    # "acculynx":    "blufire.runtime.tools.crm_acculynx",
    # "servicetitan":"blufire.runtime.tools.crm_servicetitan",
    # "ghl":         "blufire.runtime.tools.crm_ghl",
}

EMAIL_PROVIDERS: dict[str, str] = {
    "gmail": "blufire.runtime.tools.email_gmail",
    # "mailgun":     "blufire.runtime.tools.email_mailgun",
    # "sendgrid":    "blufire.runtime.tools.email_sendgrid",
    # "ses":         "blufire.runtime.tools.email_ses",
    # "ghl":         "blufire.runtime.tools.email_ghl",
}

EMAIL_DRAFT_PROVIDERS: dict[str, str] = {
    "make_webhook": "blufire.runtime.tools.email_make_webhook",
    # "gmail_api":   "blufire.runtime.tools.email_gmail_api",
    # "outlook_api": "blufire.runtime.tools.email_outlook_api",
    # "ghl":         "blufire.runtime.tools.email_ghl_draft",
}

PROSPECT_PROVIDERS: dict[str, str] = {
    "apollo": "blufire.runtime.tools.prospect_apollo",
    # "zoominfo":    "blufire.runtime.tools.prospect_zoominfo",
    # "lusha":       "blufire.runtime.tools.prospect_lusha",
}


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
    description="Drafts and sends compliant cold outreach emails to CRM contacts.",
    capabilities=(EMAIL_OUTREACH_CAPABILITY,),
)


LEAD_GENERATION_CAPABILITY = Capability(
    name="lead_generation.score_and_sync",
    tool_names=(
        "prospect.search_people",
        "llm.score_prospect",
        "crm.search_contacts",
        "crm.create_contact",
    ),
    required=True,
)

LEAD_GENERATION_BLUEPRINT = AgentBlueprint(
    name="lead_generation",
    domain="leadgen",
    description="Searches a prospect provider, scores fit with the LLM, and upserts into the CRM.",
    capabilities=(LEAD_GENERATION_CAPABILITY,),
)


CRM_PIPELINE_CAPABILITY = Capability(
    name="crm_pipeline.analyze_and_act",
    tool_names=(
        "crm.list_deals",
        "llm.analyze_pipeline",
        "crm.create_task",
    ),
    required=True,
)

CRM_PIPELINE_BLUEPRINT = AgentBlueprint(
    name="crm_pipeline",
    domain="crm",
    description="Analyzes the CRM deal pipeline and (optionally) creates follow-up tasks.",
    capabilities=(CRM_PIPELINE_CAPABILITY,),
)


DAILY_LEADGEN_CAPABILITY = Capability(
    name="daily_lead_gen.run",
    tool_names=(
        "prospect.search_people",
        "crm.search_contacts",
        "compliance.check_suppression",
        "compliance.check_send_cap",
        "crm.create_contact",
        "llm.draft_outreach_email_from_prospect",
        "compliance.build_footer",
        "compliance.record_consent",
        "email.create_draft",
    ),
    required=True,
)

DAILY_LEADGEN_BLUEPRINT = AgentBlueprint(
    name="daily_lead_gen",
    domain="leadgen",
    description=(
        "Daily compliance-gated outreach: search prospects → dedup against CRM → "
        "skip suppressed / capped → draft for human review (no auto-send)."
    ),
    capabilities=(DAILY_LEADGEN_CAPABILITY,),
)


class ProviderNotImplemented(NotImplementedError):
    """Raised when a tenant's config requests a provider whose Tool
    implementation has not been written yet. The error names the offending
    config key so operators can fix it without source-diving."""


def _load_provider_register(
    config_key: str, table_name: str, provider: str, table: dict[str, str]
) -> Callable[[ToolRegistry], None]:
    """Resolve a provider name to its ``register(tools)`` function.

    ``config_key`` is the dotted settings path the operator would edit
    (``crm.provider``, ``email.draft_provider``, …). ``table_name`` is the
    constant in this module they'd grep for (``CRM_PROVIDERS``,
    ``EMAIL_DRAFT_PROVIDERS``, …)."""
    module_path = table.get(provider)
    if module_path is None:
        raise ProviderNotImplemented(
            f"{config_key}={provider!r} is declared in settings but no Tool "
            f"implementation has been written. Add a module to "
            f"runtime/tools/, define a register(tools) function, and wire it "
            f"into bootstrap.{table_name}."
        )
    module = importlib.import_module(module_path)
    register = getattr(module, "register", None)
    if not callable(register):
        raise ProviderNotImplemented(
            f"{module_path} does not define a top-level register(tools) function."
        )
    return register  # type: ignore[no-any-return]


def _register_if_missing(registry: ToolRegistry, tool: object) -> None:
    name: str = tool.name  # type: ignore[attr-defined]
    if registry.get(name) is None:
        registry.register(tool)  # type: ignore[arg-type]


def bootstrap(
    settings: Settings | None = None,
    tools: ToolRegistry | None = None,
    capabilities: CapabilityRegistry | None = None,
) -> tuple[ToolRegistry, CapabilityRegistry]:
    """Register all built-in Tools and Capabilities for the given tenant.

    Idempotent — safe to call multiple times in the same process. The
    *first* call wins for any given tool name (re-registration is a
    no-op rather than an error).
    """
    settings = settings or get_settings()
    tools = tools or default_registry
    capabilities = capabilities or CapabilityRegistry(tools)

    # Provider-agnostic tools: same implementation for every tenant.
    for tool_cls in (
        CheckSuppressionTool,
        CheckSendCapTool,
        RecordSendTool,
        RecordConsentTool,
        BuildFooterTool,
        DraftOutreachEmailTool,
        DraftOutreachFromProspectTool,
        ScoreProspectTool,
        AnalyzePipelineTool,
    ):
        _register_if_missing(tools, tool_cls())

    # Provider-dispatched tools: pick by tenant config.
    _load_provider_register("crm.provider", "CRM_PROVIDERS", settings.crm.provider, CRM_PROVIDERS)(
        tools
    )
    _load_provider_register(
        "email.provider", "EMAIL_PROVIDERS", settings.email.provider, EMAIL_PROVIDERS
    )(tools)
    _load_provider_register(
        "email.draft_provider",
        "EMAIL_DRAFT_PROVIDERS",
        settings.email.draft_provider,
        EMAIL_DRAFT_PROVIDERS,
    )(tools)
    _load_provider_register(
        "prospect.provider",
        "PROSPECT_PROVIDERS",
        settings.prospect.provider,
        PROSPECT_PROVIDERS,
    )(tools)

    capabilities.register(EMAIL_OUTREACH_CAPABILITY)
    capabilities.register(LEAD_GENERATION_CAPABILITY)
    capabilities.register(CRM_PIPELINE_CAPABILITY)
    capabilities.register(DAILY_LEADGEN_CAPABILITY)

    return tools, capabilities
