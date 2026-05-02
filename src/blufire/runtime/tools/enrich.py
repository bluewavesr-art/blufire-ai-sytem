"""Email-enrichment tool *contract*.

Used after a prospect provider (Google Places, scraped directories, etc.)
returns a lead without an email. Implementations attempt to find an email
via website scraping (``enrich_website.py``), Hunter.io
(``enrich_hunter.py``, future), Apollo enrichment (``enrich_apollo.py``,
future), or other strategies.

The tool always returns — never raises. Callers branch on
``email is None`` and ``confidence`` to decide whether to draft an
outreach email or route the lead to a phone-only path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EmailConfidence = Literal["high", "medium", "low", "none"]


class FindEmailInput(BaseModel):
    """Either ``website_url`` or ``domain`` should be provided. Implementations
    that need a name (Hunter.io's email-finder requires it) read
    ``company_name`` and ``person_name`` for the inputs they need."""

    website_url: str | None = None
    domain: str | None = None
    company_name: str | None = None
    person_name: str | None = None


class FindEmailOutput(BaseModel):
    """``email is None`` is the no-result signal. ``confidence`` lets the
    operator triage manually-found emails differently from scraped ones.
    ``source`` names the heuristic that produced the email so we can
    debug bad finds (e.g. ``"mailto"``, ``"regex"``, ``"hunter"``)."""

    email: str | None = None
    confidence: EmailConfidence = "none"
    source: str = ""
