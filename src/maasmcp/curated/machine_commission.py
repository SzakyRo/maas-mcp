"""machine_commission: POST /api/2.0/machines/{system_id}/?op=commission."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_query_op_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachineCommissionTool:
    name = "machine_commission"
    description = (
        "Commission a machine in MAAS. "
        "Use this for direct MAAS API access when no curated verb covers it; "
        "see also deploy_machine, which commissions first when needed. "
        "Returns the MAAS response. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        enable_ssh: Annotated[
            int | None,
            Field(
                description="Whether to enable SSH for the commissioning environment "
                "using the user's SSH key(s). '1' == True, '0' == False."
            ),
        ] = None,
        skip_bmc_config: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuration of the BMC for IPMI "
                "based machines. '1' == True, '0' == False."
            ),
        ] = None,
        skip_networking: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuring the networking on the "
                "machine after the commissioning has completed. '1' == True, "
                "'0' == False."
            ),
        ] = None,
        skip_storage: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuring the storage on the "
                "machine after the commissioning has completed. '1' == True, "
                "'0' == False."
            ),
        ] = None,
        commissioning_scripts: Annotated[
            str | None,
            Field(
                description="A comma seperated list of commissioning script names "
                "and tags to be run. By default all custom commissioning scripts "
                "are run. Built-in commissioning scripts always run. Selecting "
                "'update_firmware' or 'configure_hba' will run firmware updates or "
                "configure HBA's on matching machines."
            ),
        ] = None,
        testing_scripts: Annotated[
            str | None,
            Field(
                description="A comma seperated list of testing script names and tags "
                "to be run. By default all tests tagged 'commissioning' will be "
                "run. Set to 'none' to disable running tests."
            ),
        ] = None,
        parameters: Annotated[
            str | None,
            Field(
                description="Scripts selected to run may define their own parameters. "
                "These parameters may be passed using the parameter name. Optionally "
                "a parameter may have the script name prepended to have that "
                "parameter only apply to that specific script."
            ),
        ] = None,
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
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if confirm is not True:
            raise ValueError(
                "machine_commission is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}"
            )
        path = machine_query_op_path(system_id, "commission")
        params = {
            k: v
            for k, v in {
                "enable_ssh": enable_ssh,
                "skip_bmc_config": skip_bmc_config,
                "skip_networking": skip_networking,
                "skip_storage": skip_storage,
                "commissioning_scripts": commissioning_scripts,
                "testing_scripts": testing_scripts,
                "parameters": parameters,
            }.items()
            if v is not None
        }
        return await client.post(path, json=params)  # type: ignore[no-any-return]
