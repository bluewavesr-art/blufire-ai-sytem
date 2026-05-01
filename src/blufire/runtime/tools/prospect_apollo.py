"""Apollo-backed implementation of the ``prospect.*`` contracts."""

from __future__ import annotations

from blufire.integrations.apollo import ApolloClient
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.prospect import (
    PersonRecord,
    SearchPeopleInput,
    SearchPeopleOutput,
)


class ApolloSearchPeopleTool(BaseTool[SearchPeopleInput, SearchPeopleOutput]):
    name = "prospect.search_people"
    description = "Search Apollo for prospects matching titles / locations / industries."
    input_schema = SearchPeopleInput
    output_schema = SearchPeopleOutput

    def invoke(self, ctx: RunContext, payload: SearchPeopleInput) -> SearchPeopleOutput:
        client = ApolloClient(ctx.tenant.settings)
        people: list[PersonRecord] = []
        for raw in client.search_people(
            person_titles=payload.person_titles or None,
            locations=payload.locations or None,
            industries=payload.industries or None,
            keywords=payload.keywords or None,
            max_results=payload.max_results,
        ):
            org = raw.get("organization") or {}
            people.append(
                PersonRecord(
                    email=raw.get("email"),
                    first_name=raw.get("first_name"),
                    last_name=raw.get("last_name"),
                    title=raw.get("title"),
                    company=org.get("name"),
                    raw=raw,
                )
            )
        return SearchPeopleOutput(people=people)


def register(tools: ToolRegistry) -> None:
    """Register Apollo's prospect tools. Called by bootstrap when
    ``settings.prospect.provider == "apollo"``."""
    if tools.get("prospect.search_people") is None:
        tools.register(ApolloSearchPeopleTool())
