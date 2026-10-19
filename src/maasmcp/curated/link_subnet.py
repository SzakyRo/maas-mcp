"""link_subnet: POST /nodes/{system_id}/interfaces/{id}/op-link_subnet.

Mirrors unlink_subnet but for the bind direction. Body fields:
  - subnet (int, required) — MAAS subnet id
  - mode (str, optional) — AUTO, STATIC, DHCP, or LINK_UP. Default AUTO:
    MAAS picks an IP from the subnet at deploy time. STATIC pins
    ip_address (if omitted, MAAS auto-selects one). DHCP assigns at
    deploy time from the subnet's dynamic range. LINK_UP: link-only, no IP.
  - ip_address (str, optional) — only meaningful when mode=STATIC.
  - default_gateway (bool, optional) — set this link as the machine's
    default route (only one link per machine can be default); only
    valid with AUTO/STATIC modes.
  - force (bool, optional) — ignore constraints (LINK_UP over existing
    links, linking a subnet on a different VLAN).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, _validate_ids, interface_op_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient

_LINK_MODES = ("AUTO", "STATIC", "DHCP", "LINK_UP")


class LinkSubnetTool:
    name = "link_subnet"
    description = (
        "Link a subnet to a machine interface. "
        "Use this after identifying the interface with list_interfaces or "
        "get_interface to attach a subnet with mode AUTO (MAAS assigns an IP "
        "from the subnet at deploy time), STATIC (pinned ip_address; if "
        "omitted, MAAS auto-selects one), DHCP (from the subnet's dynamic "
        "range), or LINK_UP (no IP). force=True relaxes constraints "
        "(LINK_UP over existing links, cross-VLAN links); default_gateway is "
        "only valid with AUTO/STATIC. "
        "Returns the updated MAAS interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the network interface.")],
        subnet_id: Annotated[int, Field(description="MAAS id of the subnet to link.")],
        mode: Annotated[
            Literal["AUTO", "STATIC", "DHCP", "LINK_UP"],
            Field(
                description="IP assignment mode: AUTO (MAAS picks an IP at deploy), STATIC (pinned ip_address; if ip_address is omitted, auto-selects), DHCP (dynamic range at deploy), or LINK_UP (no IP)."
            ),
        ] = "AUTO",
        ip_address: Annotated[
            str | None,
            Field(
                description="Static IP address; only meaningful when mode=STATIC, otherwise omit."
            ),
        ] = None,
        default_gateway: Annotated[
            bool | None,
            Field(
                description="If true, make this link the machine's default route. "
                "Only valid with AUTO or STATIC mode."
            ),
        ] = None,
        force: Annotated[
            bool,
            Field(
                description="If True, allows LINK_UP even when other links already exist on "
                "the interface (deleting them), and allows linking a subnet whose VLAN "
                "differs from the interface's VLAN. Defaults to False."
            ),
        ] = False,
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
    ) -> Interface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        _validate_id(subnet_id=subnet_id)
        if mode not in _LINK_MODES:
            raise ValueError(f"mode must be one of {_LINK_MODES}, got {mode!r}")
        # mode=STATIC without ip_address is valid: MAAS auto-selects an IP
        # from the subnet. (Spec: "If not provided an IP address from subnet
        # will be auto selected.")
        if mode != "STATIC" and ip_address:
            raise ValueError(f"ip_address is only meaningful with mode=STATIC, got mode={mode!r}")
        # MAAS rejects default_gateway outside AUTO/STATIC (doc: op-link_subnet).
        if default_gateway and mode not in ("AUTO", "STATIC"):
            raise ValueError(
                f"default_gateway is only valid with AUTO or STATIC mode, got mode={mode!r}"
            )
        if confirm is not True:
            raise ValueError(
                "link_subnet is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}, subnet_id={subnet_id}, mode={mode}, "
                f"ip_address={ip_address}"
            )
        body: dict[str, Any] = {"subnet": subnet_id, "mode": mode}
        if ip_address:
            body["ip_address"] = ip_address
        if default_gateway is not None:
            body["default_gateway"] = default_gateway
        if force:
            body["force"] = True
        resp = await client.post(
            interface_op_path(system_id, iface_id, "op-link_subnet"),
            json=body,
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for link_subnet response "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
