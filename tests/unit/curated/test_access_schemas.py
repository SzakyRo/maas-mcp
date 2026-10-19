"""Schema-shape tests for tag, user, and zone curated tools.

These tests mock MaasClient with AsyncMock and rely on helper functions with
explicit TypedDict return annotations so static type checkers verify that the
tool ``run()`` signatures match the expected schema shapes.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from maasmcp.curated._schemas.access import (
    BulkTagResult,
    Tag,
    User,
    Zone,
)
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.curated.tags_list import TagsListTool
from maasmcp.curated.user_read import UserReadTool
from maasmcp.curated.zones_list import ZonesListTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _mock_client() -> tuple[MaasClient, Any]:
    """Return a MaasClient-typed AsyncMock plus the underlying mock object."""
    mock: Any = AsyncMock(spec=MaasClient)
    return cast(MaasClient, mock), mock


async def test_tags_list_returns_tag_schema() -> None:
    client, mock = _mock_client()
    mock.paginated_get.return_value = [{"name": "gpu", "comment": "gpu nodes"}]

    async def _fetch(c: MaasClient) -> list[Tag]:
        result = await TagsListTool().run(c)
        assert isinstance(result, list)
        return result

    tags = await _fetch(client)
    assert tags == [{"name": "gpu", "comment": "gpu nodes"}]


async def test_user_read_returns_user_schema() -> None:
    client, mock = _mock_client()
    mock.get.return_value = {
        "id": 1,
        "username": "bob",
        "email": "bob@example.com",
        "is_superuser": False,
    }

    async def _fetch(c: MaasClient) -> User:
        result = await UserReadTool().run(c, username="bob")
        assert result is not None
        return result

    user = await _fetch(client)
    assert user["username"] == "bob"
    assert user["email"] == "bob@example.com"


async def test_zones_list_returns_zone_schema() -> None:
    client, mock = _mock_client()
    mock.paginated_get.return_value = [{"id": 1, "name": "default", "description": None}]

    async def _fetch(c: MaasClient) -> list[Zone]:
        result = await ZonesListTool().run(c)
        assert isinstance(result, list)
        return result

    zones = await _fetch(client)
    assert zones == [{"id": 1, "name": "default", "description": None}]


async def test_bulk_tag_machines_returns_bulk_tag_result_schema() -> None:
    client, mock = _mock_client()
    mock.post.return_value = None

    async def _fetch(c: MaasClient) -> list[BulkTagResult]:
        return await BulkTagMachinesTool().run(c, system_ids=["abc123"], tag="gpu", confirm=True)

    results = await _fetch(client)
    assert results == [{"system_id": "abc123", "status": "ok", "result": None}]
