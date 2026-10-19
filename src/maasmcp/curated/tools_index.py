"""tools_index: discoverability helper returning a grouped tool catalog."""

from __future__ import annotations

from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._catalog import ToolsIndexResponse
from maasmcp.maas.client import MaasClient


class ToolsIndexTool:
    name = "tools_index"
    description = (
        "Return a grouped catalog of all available MAAS tools. "
        "Use this when you are unsure which tool to call. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        # The rebind wrapper requires every tool to accept the injected client,
        # even though this meta tool never calls MAAS.
        client: Annotated[MaasClient, SkipJsonSchema()],
    ) -> ToolsIndexResponse:
        from maasmcp.curated._common import TOOL_INDEX

        return TOOL_INDEX
