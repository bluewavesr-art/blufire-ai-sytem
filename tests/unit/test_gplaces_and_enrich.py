"""Tests for the Places prospect provider and the website-scrape email
enricher. Both stub the underlying clients with in-memory fakes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from blufire.runtime.bootstrap import ENRICH_PROVIDERS, PROSPECT_PROVIDERS, bootstrap
from blufire.runtime.capability import CapabilityRegistry
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools.enrich import FindEmailInput
from blufire.runtime.tools.enrich_website import WebsiteFindEmailTool, _looks_real
from blufire.runtime.tools.prospect import SearchPeopleInput
from blufire.runtime.tools.prospect_gplaces import GPlacesSearchPeopleTool, _split_address


def _ctx(settings: Any) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="t", run_id="r")


# ---------------------------------------------------------------------------
# Address parsing
# ---------------------------------------------------------------------------


def test_split_address_us_format() -> None:
    street, city, state = _split_address("123 Main St, Fort Worth, TX 76102, USA")
    assert street == "123 Main St"
    assert city == "Fort Worth"
    assert state == "TX"


def test_split_address_short_returns_unsplit() -> None:
    street, city, state = _split_address("Just a name")
    # Single-segment input — keep the original as the street, blank rest.
    assert street == "Just a name"
    assert city is None
    assert state is None


def test_split_address_empty() -> None:
    assert _split_address(None) == (None, None, None)
    assert _split_address("") == (None, None, None)


# ---------------------------------------------------------------------------
# Places prospect provider
# ---------------------------------------------------------------------------


class _FakePlaces:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits

    def search(
        self,
        query: str,
        *,
        location: str | None = None,
        max_results: int = 25,
    ):
        # Yield up to max_results — caller's per-location budget.
        yield from self._hits[:max_results]


@pytest.fixture
def places_settings(tmp_settings: Any) -> Any:
    tmp_settings.prospect.provider = "gplaces"  # type: ignore[assignment]
    tmp_settings.secrets.gplaces_api_key = "test-key"  # type: ignore[assignment]
    return tmp_settings


def test_gplaces_maps_hit_to_person_record(places_settings: Any) -> None:
    fake = _FakePlaces(
        [
            {
                "place_id": "p1",
                "name": "ACME Property Mgmt",
                "formatted_address": "100 Main St, Fort Worth, TX 76102, USA",
                "formatted_phone_number": "(817) 555-1234",
                "website": "https://acme.test",
            }
        ]
    )
    with patch("blufire.runtime.tools.prospect_gplaces.GPlacesClient", return_value=fake):
        out = GPlacesSearchPeopleTool().invoke(
            _ctx(places_settings),
            SearchPeopleInput(person_titles=["property management"], locations=["Fort Worth"]),
        )
    assert len(out.people) == 1
    p = out.people[0]
    assert p.email is None  # Places never returns emails
    assert p.company == "ACME Property Mgmt"
    assert p.phone == "(817) 555-1234"
    assert p.address == "100 Main St"
    assert p.city == "Fort Worth"
    assert p.state == "TX"
    assert p.website == "https://acme.test"
    assert p.raw["place_id"] == "p1"  # raw payload preserved


def test_gplaces_dedups_by_place_id(places_settings: Any) -> None:
    """Same place_id appearing in two location queries returns one record."""
    fake = _FakePlaces(
        [
            {"place_id": "p1", "name": "ACME", "formatted_address": "1 St, City, TX 0, USA"},
            {"place_id": "p1", "name": "ACME again", "formatted_address": "1 St, City, TX 0, USA"},
        ]
    )
    with patch("blufire.runtime.tools.prospect_gplaces.GPlacesClient", return_value=fake):
        out = GPlacesSearchPeopleTool().invoke(
            _ctx(places_settings), SearchPeopleInput(locations=["Fort Worth"])
        )
    assert len(out.people) == 1


# ---------------------------------------------------------------------------
# Website enrichment
# ---------------------------------------------------------------------------


def test_looks_real_blocks_assets() -> None:
    assert not _looks_real("logo@2x.png")
    assert not _looks_real("hello@example.com")
    assert not _looks_real("noreply@gmail.com")
    assert _looks_real("info@acme.com")
    assert _looks_real("sales@my-business.io")


def test_website_enricher_finds_mailto_link(tmp_settings: Any) -> None:
    """A homepage with a mailto link is the high-confidence path."""

    class _Resp:
        status_code = 200
        text = '<html><body><a href="mailto:owner@acme.com">Email Us</a></body></html>'

    with patch("blufire.runtime.tools.enrich_website.build_session") as mock_session:
        mock_session.return_value.get.return_value = _Resp()
        mock_session.return_value.headers.update.return_value = None
        out = WebsiteFindEmailTool().invoke(
            _ctx(tmp_settings),
            FindEmailInput(website_url="https://acme.com"),
        )
    assert out.email == "owner@acme.com"
    assert out.confidence == "high"


def test_website_enricher_falls_back_to_regex(tmp_settings: Any) -> None:
    """No mailto, but a visible info@ in plain text → medium confidence."""

    class _Resp:
        status_code = 200
        text = "<html><body>Reach us at info@acme.com or call us</body></html>"

    with patch("blufire.runtime.tools.enrich_website.build_session") as mock_session:
        mock_session.return_value.get.return_value = _Resp()
        mock_session.return_value.headers.update.return_value = None
        out = WebsiteFindEmailTool().invoke(
            _ctx(tmp_settings),
            FindEmailInput(website_url="https://acme.com"),
        )
    assert out.email == "info@acme.com"
    assert out.confidence == "medium"


def test_website_enricher_returns_none_when_nothing_found(tmp_settings: Any) -> None:
    class _Resp:
        status_code = 200
        text = "<html><body>No emails here at all.</body></html>"

    with patch("blufire.runtime.tools.enrich_website.build_session") as mock_session:
        mock_session.return_value.get.return_value = _Resp()
        mock_session.return_value.headers.update.return_value = None
        out = WebsiteFindEmailTool().invoke(
            _ctx(tmp_settings), FindEmailInput(website_url="https://acme.com")
        )
    assert out.email is None
    assert out.confidence == "none"


def test_website_enricher_skips_when_no_url(tmp_settings: Any) -> None:
    out = WebsiteFindEmailTool().invoke(_ctx(tmp_settings), FindEmailInput(website_url=None))
    assert out.email is None
    assert out.source == "no_website"


# ---------------------------------------------------------------------------
# Bootstrap dispatch
# ---------------------------------------------------------------------------


def test_gplaces_is_registered_in_dispatch() -> None:
    assert "gplaces" in PROSPECT_PROVIDERS
    assert PROSPECT_PROVIDERS["gplaces"] == "blufire.runtime.tools.prospect_gplaces"


def test_website_enricher_is_default(tmp_settings: Any) -> None:
    assert tmp_settings.enrich.provider == "website"
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    tool = tools.get("enrich.find_email")
    assert tool is not None
    assert type(tool).__name__ == "WebsiteFindEmailTool"


def test_enrich_dispatch_table_only_runtime_paths() -> None:
    for provider, module_path in ENRICH_PROVIDERS.items():
        assert isinstance(provider, str) and provider
        assert module_path.startswith("blufire.runtime.tools.")
