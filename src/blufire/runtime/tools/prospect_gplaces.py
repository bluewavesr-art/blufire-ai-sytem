"""Google Places-backed implementation of ``prospect.search_people``.

Different shape from Apollo: Places is a *business* directory, not a
*people* directory. We map each Place into a PersonRecord whose
``company`` is the business name and whose person fields (first_name /
last_name / title) are blank. Email is always None — that's why the
orchestrator runs the enrichment step after this provider.

The Places query is built from the ProspectSearch config:

* ``person_titles`` becomes search terms (e.g. ["property management",
  "facilities maintenance"]). For Places, "titles" really means
  business types.
* ``locations`` is appended to the query as a city bias, one query per
  configured location so different metros don't blur together.
* ``industries`` and ``keywords`` are folded into the query string.
* ``per_page`` becomes max_results.
"""

from __future__ import annotations

from blufire.integrations.gplaces import GPlacesClient
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.prospect import (
    PersonRecord,
    SearchPeopleInput,
    SearchPeopleOutput,
)


def _split_address(formatted: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a Google-formatted US address into (street, city, state).

    Format is ``"<street>, <city>, <state> <zip>, <country>"`` for US
    results. Returns (None, None, None) if the format isn't recognized
    so callers can fall back to the unsplit string."""
    if not formatted:
        return None, None, None
    parts = [p.strip() for p in formatted.split(",")]
    if len(parts) < 3:
        return formatted, None, None
    street = parts[0] or None
    city = parts[1] or None
    state_zip = parts[2].strip()
    state = state_zip.split()[0] if state_zip else None
    return street, city, state


class GPlacesSearchPeopleTool(BaseTool[SearchPeopleInput, SearchPeopleOutput]):
    name = "prospect.search_people"
    description = (
        "Search Google Places for local businesses matching the configured "
        "titles/keywords/locations. Returns name, phone, address, website "
        "(no email — pair with enrich.find_email)."
    )
    input_schema = SearchPeopleInput
    output_schema = SearchPeopleOutput

    def invoke(self, ctx: RunContext, payload: SearchPeopleInput) -> SearchPeopleOutput:
        client = GPlacesClient(ctx.tenant.settings)
        # Build a simple query: combine titles/keywords/industries into one
        # phrase, then issue one search per location. Places' text search
        # is forgiving — too-narrow ANDed terms hurt recall more than they
        # help precision.
        query_parts = (
            list(payload.person_titles) + list(payload.keywords) + list(payload.industries)
        )
        query = " ".join(p for p in query_parts if p) or "local business"
        locations = list(payload.locations) or [None]

        people: list[PersonRecord] = []
        seen_place_ids: set[str] = set()
        per_location_cap = max(1, payload.max_results // max(len(locations), 1))

        for loc in locations:
            for hit in client.search(query, location=loc, max_results=per_location_cap):
                place_id = hit.get("place_id")
                if not place_id or place_id in seen_place_ids:
                    continue
                seen_place_ids.add(place_id)

                street, city, state = _split_address(hit.get("formatted_address"))
                people.append(
                    PersonRecord(
                        email=None,
                        first_name=None,
                        last_name=None,
                        title=None,
                        company=hit.get("name"),
                        phone=hit.get("formatted_phone_number"),
                        address=street,
                        city=city,
                        state=state,
                        website=hit.get("website"),
                        raw=hit,
                    )
                )
                if len(people) >= payload.max_results:
                    return SearchPeopleOutput(people=people)

        return SearchPeopleOutput(people=people)


def register(tools: ToolRegistry) -> None:
    """Register the Google Places prospect tool. Called by bootstrap when
    ``settings.prospect.provider == "gplaces"``."""
    if tools.get("prospect.search_people") is None:
        tools.register(GPlacesSearchPeopleTool())
