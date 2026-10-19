"""get_machine: boot_disk field surfacing tests.

The machine-dict read path is exercised in tests/unit/test_curated.py; here
we only cover the boot_disk_id/boot_disk_name normalization added so
agents can discover what's pinned without dropping to raw API.

Note: get_machine routes identifiers based on a hex-ish heuristic (all
chars in 0-9a-f, length ≥ 6). We use "abcdef" to hit the direct
GET /machines/{id}/ path so respx mocks are straightforward.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.get_machine import GetMachineTool
from maasmcp.maas.client import MaasClient

_SYSTEM_ID = "abcdef"  # passes hex heuristic → direct /machines/{id}/ path


def _machine_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "system_id": _SYSTEM_ID,
        "hostname": "rich-gator",
        "tag_names": [],
        "pool": {"name": "default"},
        "owner": {"username": "admin"},
        "power_state": "off",
        "osystem": "ubuntu",
        "distro_series": "jammy",
        "last_commissioned": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_unsafe_identifier_rejected_without_http(maas_client: MaasClient) -> None:
    """identifier is interpolated into the URL path on the direct-fetch
    branches, so it must pass the same safe-segment validation other machine
    tools apply — path traversal / query smuggling never reach the wire."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            for bad in ["../x", "a/b", "a?x=1", "a#frag", ""]:
                with pytest.raises(ValueError, match="system_id"):
                    await GetMachineTool().run(maas_client, identifier=bad)
    assert not mock.calls


@pytest.mark.asyncio
async def test_os_field_is_stripped(maas_client: MaasClient) -> None:
    """osystem/distro_series concatenation must not yield leading/bare
    spaces when one or both fields are missing."""
    payload = _machine_payload(osystem="", distro_series="")
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier=_SYSTEM_ID)
    assert result["os"] == ""


@pytest.mark.asyncio
async def test_boot_disk_as_embedded_dict(maas_client: MaasClient) -> None:
    payload = _machine_payload(boot_disk={"id": 1, "name": "sda", "path": "/dev/sda"})
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier=_SYSTEM_ID)
    assert result["boot_disk_id"] == 1
    assert result["boot_disk_name"] == "sda"


@pytest.mark.asyncio
async def test_boot_disk_as_scalar_int(maas_client: MaasClient) -> None:
    """Some MAAS responses return boot_disk as a scalar id rather than an
    embedded dict. The tool must not crash on either shape."""
    payload = _machine_payload(boot_disk=7)
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier=_SYSTEM_ID)
    assert result["boot_disk_id"] == 7
    assert result["boot_disk_name"] is None


@pytest.mark.asyncio
async def test_boot_disk_unset(maas_client: MaasClient) -> None:
    """boot_disk field present but null maps to None/None."""
    payload = _machine_payload(boot_disk=None)
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier=_SYSTEM_ID)
    assert result["boot_disk_id"] is None
    assert result["boot_disk_name"] is None
