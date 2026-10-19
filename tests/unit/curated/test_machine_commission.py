import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.machine_commission import MachineCommissionTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_machine_commission_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/abc/?op=commission").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachineCommissionTool().run(maas_client, system_id="abc")
    assert not route.called


async def test_machine_commission_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/abc/?op=commission").mock(
            return_value=Response(200, json={"status_name": "Commissioning"})
        )
        async with maas_client:
            result = await MachineCommissionTool().run(
                maas_client,
                system_id="abc",
                enable_ssh=1,
                skip_storage=0,
                testing_scripts="none",
                confirm=True,
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert 'name="enable_ssh"' in body
    assert 'name="skip_storage"' in body
    assert 'name="testing_scripts"' in body
    assert 'name="confirm"' not in body
    assert result == {"status_name": "Commissioning"}


async def test_machine_commission_omits_none_params(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/abc/?op=commission").mock(
            return_value=Response(200, json={"status_name": "Commissioning"})
        )
        async with maas_client:
            result = await MachineCommissionTool().run(maas_client, system_id="abc", confirm=True)
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert 'name="' not in body
    assert result == {"status_name": "Commissioning"}
