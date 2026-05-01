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
