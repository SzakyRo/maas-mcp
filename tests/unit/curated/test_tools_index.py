"""Unit tests for the tools_index discoverability tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from maasmcp.curated.tools_index import ToolsIndexTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_tools_index_returns_grouped_response() -> None:
    client = AsyncMock(spec=MaasClient)
    result = await ToolsIndexTool().run(client)

    assert "meta" in result.groups
    assert "machines" in result.groups
    assert any(entry.name == "tools_index" for entry in result.groups["meta"])


@pytest.mark.asyncio
async def test_tools_index_entries_have_metadata() -> None:
    client = AsyncMock(spec=MaasClient)
    result = await ToolsIndexTool().run(client)

    for group in result.groups.values():
        for entry in group:
            assert entry.name
            assert entry.title
            assert entry.description
            assert entry.read_only is not None
            assert entry.destructive is not None
