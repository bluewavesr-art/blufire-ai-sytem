"""CRM tool *contracts* — pydantic schemas every CRM backend must satisfy.

Implementations live in sibling modules (``crm_hubspot.py``,
``crm_jobber.py``, ``crm_acculynx.py``, ``crm_servicetitan.py``, …) and
are wired into the registry by ``runtime/bootstrap.py`` based on
``settings.crm.provider``.

The orchestrator never imports a CRM-specific implementation. It calls
``registry.get("crm.list_contacts")`` and the configured provider is
returned. Adding a new CRM = one new module + one line in bootstrap.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

DEFAULT_CONTACT_PROPERTIES = ["firstname", "lastname", "email", "company", "jobtitle"]


# ---------------------------------------------------------------------------
# crm.list_contacts
# ---------------------------------------------------------------------------


class ListContactsInput(BaseModel):
    properties: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTACT_PROPERTIES))
    limit: int = Field(default=10, ge=1, le=500)


class ContactRecord(BaseModel):
    """Provider-agnostic contact shape. Implementations map their native
    record (HubSpot Contact, Jobber Client, AccuLynx Customer, ServiceTitan
    Customer, …) into this shape."""

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ListContactsOutput(BaseModel):
    contacts: list[ContactRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# crm.log_email
# ---------------------------------------------------------------------------


class LogEmailInput(BaseModel):
    contact_id: str
    subject: str
    body: str


class LogEmailOutput(BaseModel):
    """``logged=False`` is a soft failure: either the CRM doesn't support
    logging (some field-service CRMs are read-mostly) or the call timed out.
    The orchestrator logs a warning and continues — it never fails the
    overall send because of a logging miss."""

    logged: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# crm.search_contacts
# ---------------------------------------------------------------------------


class SearchContactsInput(BaseModel):
    email: str
    properties: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTACT_PROPERTIES))


class SearchContactsOutput(BaseModel):
    contacts: list[ContactRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# crm.create_contact
# ---------------------------------------------------------------------------


class CreateContactInput(BaseModel):
    properties: dict[str, Any] = Field(default_factory=dict)


class CreateContactOutput(BaseModel):
    """``contact_id`` is None when the contact already existed (HubSpot 409
    or equivalent). Callers treat this as a soft de-dup signal, not a failure."""

    contact_id: str | None = None
    already_existed: bool = False


# ---------------------------------------------------------------------------
# crm.list_deals
# ---------------------------------------------------------------------------


DEFAULT_DEAL_PROPERTIES = [
    "dealname",
    "dealstage",
    "amount",
    "closedate",
    "pipeline",
    "hubspot_owner_id",
    "hs_lastmodifieddate",
]


class ListDealsInput(BaseModel):
    properties: list[str] = Field(default_factory=lambda: list(DEFAULT_DEAL_PROPERTIES))
    limit: int = Field(default=50, ge=1, le=500)


class DealRecord(BaseModel):
    """Provider-agnostic deal shape. Implementations map their native deal
    object (HubSpot Deal, ServiceTitan Job, Jobber Quote, …) into this shape."""

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ListDealsOutput(BaseModel):
    deals: list[DealRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# crm.update_deal
# ---------------------------------------------------------------------------


class UpdateDealInput(BaseModel):
    deal_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class UpdateDealOutput(BaseModel):
    updated: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# crm.create_deal
# ---------------------------------------------------------------------------


class CreateDealInput(BaseModel):
    dealname: str
    stage: str
    amount: float | None = None
    contact_id: str | None = None


class CreateDealOutput(BaseModel):
    deal_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# crm.create_task
# ---------------------------------------------------------------------------


class CreateTaskInput(BaseModel):
    title: str
    contact_id: str | None = None
    due_days: int = Field(default=3, ge=0, le=365)


class CreateTaskOutput(BaseModel):
    task_id: str | None = None
    created: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# crm.append_call_lead
#
# Output sink for prospects we couldn't find an email for. The
# orchestrator routes them here so the team can phone or visit instead
# of cold-emailing. Backends typically append to a "Call List" sheet
# with name, phone, address, and a one-line opener generated by the
# LLM as a talking-point hint.
# ---------------------------------------------------------------------------


class AppendCallLeadInput(BaseModel):
    company: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    website: str | None = None
    talking_points: str = ""  # one-line context for the caller, LLM-generated


class AppendCallLeadOutput(BaseModel):
    appended: bool
    error: str | None = None
