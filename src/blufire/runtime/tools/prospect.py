"""Prospect-search tool *contracts*. Implementations live in sibling modules
(``prospect_apollo.py``, ``prospect_zoominfo.py``, …) and are wired into the
registry by ``runtime/bootstrap.py`` based on ``settings.prospect.provider``.

A prospect is a person we don't yet have in our CRM but who matches our
ideal-customer-profile criteria. The contract is intentionally narrow:
search by titles / locations / industries, return enriched person records.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchPeopleInput(BaseModel):
    person_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    max_results: int = Field(default=25, ge=1, le=500)


class PersonRecord(BaseModel):
    """Provider-agnostic prospect shape. Implementations map their native
    record (Apollo Person, ZoomInfo Contact, …) into this shape. The
    ``raw`` dict carries provider-specific fields the orchestrator may pass
    through to downstream tools (e.g. organization details for the LLM
    scorer)."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SearchPeopleOutput(BaseModel):
    people: list[PersonRecord] = Field(default_factory=list)
