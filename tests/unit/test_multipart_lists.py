"""Tests for MaasClient multipart body handling: list values produce
repeated multipart parts with the same name (MAAS contract).
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasConfig
from maasmcp.maas.client import MaasClient


def _cfg() -> MaasConfig:
    return MaasConfig(base_url="https://maas.example.com/MAAS", api_key="k")


@respx.mock
@pytest.mark.asyncio
async def test_post_list_value_produces_repeated_parts():
    route = respx.post("https://maas.example.com/MAAS/api/2.0/x/").mock(
        return_value=Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await client.post("/api/2.0/x/", json={"parents": [2, 3]})
    sent_body = route.calls.last.request.read().decode()
    assert sent_body.count('name="parents"') == 2
    assert "2" in sent_body
    assert "3" in sent_body
    assert "[2, 3]" not in sent_body


@respx.mock
@pytest.mark.asyncio
async def test_post_scalar_value_single_part():
    route = respx.post("https://maas.example.com/MAAS/api/2.0/x/").mock(
        return_value=Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await client.post("/api/2.0/x/", json={"name": "bond0"})
    sent_body = route.calls.last.request.read().decode()
    assert sent_body.count('name="name"') == 1
    assert "bond0" in sent_body


@respx.mock
@pytest.mark.asyncio
async def test_post_bool_renders_as_true_false():
    """Python's str(True) is 'True'; MAAS rejects that. We render 'true'."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/x/").mock(
        return_value=Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await client.post("/api/2.0/x/", json={"erase": True, "force": False})
    sent_body = route.calls.last.request.read().decode()
    assert "true" in sent_body
    assert "false" in sent_body
    assert '"True"' not in sent_body
    assert '"False"' not in sent_body


@respx.mock
@pytest.mark.asyncio
async def test_put_list_value_also_repeated():
    """PUT (e.g. assign_vlan_to_interface on parents, etc.) must do the same."""
    route = respx.put("https://maas.example.com/MAAS/api/2.0/x/").mock(
        return_value=Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await client.put("/api/2.0/x/", json={"tags": ["a", "b", "c"]})
    sent_body = route.calls.last.request.read().decode()
    assert sent_body.count('name="tags"') == 3


@respx.mock
@pytest.mark.asyncio
async def test_empty_list_value_produces_no_parts():
    """An empty list is a valid (no-op) value — no parts emitted."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/x/").mock(
        return_value=Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await client.post("/api/2.0/x/", json={"parents": []})
    sent_body = route.calls.last.request.read().decode()
    assert 'name="parents"' not in sent_body
