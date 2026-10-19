"""machine_details: GET /machines/{system_id}/?op=details."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachineDetailsTool:
    name = "machine_details"
    description = (
        "Fetch commissioning hardware-detail dumps (LLDP, lshw XML) for a "
        "machine via GET machines/{system_id}/?op=details. "
        "Returns a {detail_type: xml} map (e.g. 'lldp', 'lshw'); MAAS serves this "
        "as BSON rather than JSON (JSON can't carry binary efficiently), so the "
        "response may surface as raw text, not a parsed dict. "
        "Use get_machine for the regular machine record — this op does NOT "
        "return machine-record fields. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> dict[str, Any] | str | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        # ``op`` travels in the params dict, not the URL: httpx replaces the
        # URL query string wholesale when ``params=`` is passed, which would
        # silently drop an in-path ``?op=details``.
        params = {"op": "details"}
        return await client.get(  # type: ignore[no-any-return]
            machine_path(system_id),
            params=params,
        )
