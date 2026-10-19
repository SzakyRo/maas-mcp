"""configure_link: one-call repair of a DOWN physical link.

Composite write for the cross-links topology where a machine always
presents paired 10G links (e.g. Application UP / Storage UP /
Application DOWN / Storage UP). Given the iface_id of the DOWN link
— obtained from a prior ``list_interfaces`` discovery call — this tool:

1. pre-flight GETs the interface (refuses non-physical types),
2. if it already matches the desired state, returns ``changed=False``
   without writing (idempotent),
3. otherwise issues ONE atomic PUT carrying ``link_connected=True``,
   ``link_speed``/``interface_speed``, and the VLAN — MAAS applies the
   whole body atomically, so the logical connect → speed → VLAN order
   is a contract of the tool, not a wire sequence,
4. post-flight GETs to verify the state actually landed and reports
   ``verified=False`` on drift instead of trusting the PUT echo.

The VLAN is specified as the IEEE 802.1Q VID (e.g. 79) and translated
to MAAS's internal primary key via ``_resolve_vlan_id`` — same
convention as :class:`AssignVlanToInterfaceTool` and
:class:`UpdateInterfaceTool`.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _resolve_vlan_id,
    _validate_id,
    _validate_ids,
    interface_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient

_SNAPSHOT_FIELDS = ("link_connected", "link_speed", "interface_speed", "vlan_id")


def _snapshot(iface: dict[str, Any]) -> dict[str, Any]:
    """Extract the desired-state fields from an interface dict."""
    return {f: iface.get(f) for f in _SNAPSHOT_FIELDS}


def _matches_desired(iface: dict[str, Any], speed_mbps: int, maas_vlan_id: int) -> bool:
    """True when the interface dict already carries the desired state."""
    return (
        iface.get("link_connected") is True
        and iface.get("link_speed") == speed_mbps
        and iface.get("interface_speed") == speed_mbps
        and iface.get("vlan_id") == maas_vlan_id
    )


class ConfigureLinkTool:
    name = "configure_link"
    description = (
        "Bring a DOWN physical link up in one call: set it connected, set "
        "link/interface speed (default 10000 Mbps = 10G), and assign its "
        "untagged VLAN by IEEE 802.1Q VID — one atomic PUT plus pre/post "
        "verification. "
        "Built for the cross-links topology (Application/Storage link pairs "
        "where one Application link reports DOWN at 10G): discover the down "
        "interface's id first with list_interfaces, then call this. "
        "Refuses non-physical interfaces (bond/bridge/vlan); no-op with "
        "changed=False when the interface already matches; verified=False "
        "means the post-write readback disagrees with the desired state. "
        "Returns dict with iface_id, name, previous state, interface, "
        "changed, verified. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the interface to configure.")],
        vid: Annotated[int, Field(description="IEEE 802.1Q VLAN ID (vid) to assign.")],
        speed_mbps: Annotated[
            int,
            Field(
                description="Link/interface speed in Mbps (default 10000 = 10G). "
                "Sets BOTH link_speed and interface_speed in one request."
            ),
        ] = 10000,
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> dict[str, Any]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        _validate_id(vid=vid)
        _validate_id(speed_mbps=speed_mbps)
        if confirm is not True:
            raise ValueError(
                "configure_link is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}, vid={vid}, speed_mbps={speed_mbps}"
            )

        url = interface_path(system_id, iface_id)
        before = await client.get(url)
        if not isinstance(before, dict):
            raise ValueError(
                f"MAAS returned non-dict for interface {iface_id} "
                f"(got {type(before).__name__}); schema drift?"
            )
        if before.get("type") != "physical":
            raise ValueError(
                f"configure_link only handles physical interfaces; "
                f"iface_id={iface_id} is type {before.get('type')!r}. "
                "Configure the underlying members instead."
            )

        maas_vlan_id = await _resolve_vlan_id(client, vid)
        previous = _snapshot(before)

        if _matches_desired(before, speed_mbps, maas_vlan_id):
            return {
                "iface_id": iface_id,
                "name": before.get("name"),
                "previous": previous,
                "interface": before,
                "changed": False,
                "verified": True,
            }

        resp = await client.put(
            url,
            json={
                "link_connected": True,
                "link_speed": speed_mbps,
                "interface_speed": speed_mbps,
                "vlan": maas_vlan_id,
            },
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated interface "
                f"(got {type(resp).__name__}); schema drift?"
            )

        after = await client.get(url)
        verified = isinstance(after, dict) and _matches_desired(after, speed_mbps, maas_vlan_id)
        return {
            "iface_id": iface_id,
            "name": resp.get("name"),
            "previous": previous,
            "interface": after if isinstance(after, dict) else resp,
            "changed": True,
            "verified": verified,
        }
