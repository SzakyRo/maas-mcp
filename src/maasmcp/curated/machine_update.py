"""machine_update: PUT /machines/{system_id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.maas.client import MaasClient


class MachineUpdateTool:
    name = "machine_update"
    description = (
        "Update a machine in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; call "
        "get_machine to confirm the target first. "
        "Returns the MAAS response. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise. "
        "NOTE: its 'hostname' field sets the machine's new name — to target by "
        "hostname, resolve via get_machine first."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[str, Field(description="MAAS system_id of the machine.")],
        hostname: Annotated[
            str | None, Field(description="The new hostname for this machine.")
        ] = None,
        description: Annotated[
            str | None, Field(description="The new description for this machine.")
        ] = None,
        domain: Annotated[
            str | None,
            Field(
                description="The domain for this machine. If not given the default domain is used."
            ),
        ] = None,
        architecture: Annotated[
            str | None, Field(description="The new architecture for this machine.")
        ] = None,
        min_hwe_kernel: Annotated[
            str | None,
            Field(
                description="A string containing the minimum kernel version allowed to be ran on this machine."
            ),
        ] = None,
        power_type: Annotated[
            str | None,
            Field(
                description="The new power type for this machine. If you use the default value, power_parameters will be set to the empty string.  Available to admin users.  See the `Power types`_ section for a list of the available power types."
            ),
        ] = None,
        power_parameters_skip_check: Annotated[
            bool | None,
            Field(
                description="Whether or not the new power parameters for this machine should be checked against the expected power parameters for the machine's power type ('true' or 'false').  The default is 'false'."
            ),
        ] = None,
        pool: Annotated[
            str | None,
            Field(
                description="The resource pool to which the machine should belong. All machines belong to the 'default' resource pool if they do not belong to any other resource pool."
            ),
        ] = None,
        zone: Annotated[
            str | None,
            Field(description="Name of a valid physical zone in which to place this machine."),
        ] = None,
        swap_size: Annotated[
            str | None,
            Field(
                description="Specifies the size of the swap file, in bytes. Field accept K, M, G and T suffixes for values expressed respectively in kilobytes, megabytes, gigabytes and terabytes."
            ),
        ] = None,
        disable_ipv4: Annotated[
            bool | None, Field(description="Deprecated. If specified, must be false.")
        ] = None,
        cpu_count: Annotated[
            int | None, Field(description="The amount of CPU cores the machine has.")
        ] = None,
        memory: Annotated[
            str | None,
            Field(
                description="How much memory the machine has.  Field accept K, M, G and T suffixes for values expressed respectively in kilobytes, megabytes, gigabytes and terabytes."
            ),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        validate_system_id(system_id)
        if confirm is not True:
            raise ValueError(
                "machine_update is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}"
            )
        body = {
            k: v
            for k, v in {
                "hostname": hostname,
                "description": description,
                "domain": domain,
                "architecture": architecture,
                "min_hwe_kernel": min_hwe_kernel,
                "power_type": power_type,
                "power_parameters_skip_check": power_parameters_skip_check,
                "pool": pool,
                "zone": zone,
                "swap_size": swap_size,
                "disable_ipv4": disable_ipv4,
                "cpu_count": cpu_count,
                "memory": memory,
            }.items()
            if v is not None
        }
        return await client.put(  # type: ignore[no-any-return]
            machine_path(system_id), json=body
        )
