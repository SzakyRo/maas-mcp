"""machines_create: POST /machines/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class MachinesCreateTool:
    name = "machines_create"
    description = (
        "Create machines in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; call "
        "list_machines afterwards to confirm the new machine. "
        "Returns the MAAS response. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        architecture: Annotated[
            str,
            Field(
                description='A string containing the architecture type of the machine (for example, "i386" or "amd64").'
            ),
        ],
        mac_addresses: Annotated[
            str | list[str],
            Field(
                description="One or more MAC addresses for the machine, as a list. "
                "MAAS expects repeated 'mac_addresses' fields; a list here becomes "
                'repeated parts (e.g. ["01:02:03:04:05:06", "02:03:04:05:06:07"]).'
            ),
        ],
        min_hwe_kernel: Annotated[
            str | None,
            Field(
                description="A string containing the minimum kernel version allowed to be ran on this machine."
            ),
        ] = None,
        subarchitecture: Annotated[
            str | None,
            Field(
                description='A string containing the subarchitecture type of the machine. (For example, "generic" or "hwe-t".) To determine the supported subarchitectures, use the boot-resources endpoint.'
            ),
        ] = None,
        hostname: Annotated[
            str | None, Field(description="A hostname. If not given, one will be generated.")
        ] = None,
        description: Annotated[str | None, Field(description="A optional description.")] = None,
        domain: Annotated[
            str | None,
            Field(
                description="The domain of the machine. If not given the default domain is used."
            ),
        ] = None,
        power_type: Annotated[
            str | None,
            Field(description='A power management type, if applicable (e.g. "virsh", "ipmi").'),
        ] = None,
        commission: Annotated[
            bool | None,
            Field(
                description="Request the newly created machine to be created with status set to COMMISSIONING. Machines will wait for COMMISSIONING results and not time out. Machines created by administrators will be commissioned unless set to false."
            ),
        ] = None,
        deployed: Annotated[
            bool | None,
            Field(
                description="Request the newly created machine to be created with status set to DEPLOYED. Setting this to true implies commissioning=false, meaning that the machine won't go through the commissioning process."
            ),
        ] = None,
        enable_ssh: Annotated[
            int | None,
            Field(
                description="Whether to enable SSH for the commissioning environment using the user's SSH key(s). '1' == True, '0' == False."
            ),
        ] = None,
        skip_bmc_config: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuration of the BMC for IPMI based machines. '1' == True, '0' == False."
            ),
        ] = None,
        skip_networking: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuring the networking on the machine after the commissioning has completed. '1' == True, '0' == False."
            ),
        ] = None,
        skip_storage: Annotated[
            int | None,
            Field(
                description="Whether to skip re-configuring the storage on the machine after the commissioning has completed. '1' == True, '0' == False."
            ),
        ] = None,
        commissioning_scripts: Annotated[
            str | None,
            Field(
                description="A comma seperated list of commissioning script names and tags to be run. By default all custom commissioning scripts are run. Built-in commissioning scripts always run. Selecting 'update_firmware' or 'configure_hba' will run firmware updates or configure HBA's on matching machines."
            ),
        ] = None,
        is_dpu: Annotated[
            bool | None,
            Field(
                description="Whether the machine is a DPU or not. If not provided, the machine is considered a non-DPU machine."
            ),
        ] = None,
        testing_scripts: Annotated[
            str | None,
            Field(
                description="A comma seperated list of testing script names and tags to be run. By default all tests tagged 'commissioning' will be run. Set to 'none' to disable running tests."
            ),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        if confirm is not True:
            raise ValueError(
                "machines_create is destructive; pass confirm=True to proceed. "
                f"Affected: architecture={architecture}, mac_addresses={mac_addresses}"
            )
        body = {
            k: v
            for k, v in {
                "architecture": architecture,
                "min_hwe_kernel": min_hwe_kernel,
                "subarchitecture": subarchitecture,
                "mac_addresses": mac_addresses,
                "hostname": hostname,
                "description": description,
                "domain": domain,
                "power_type": power_type,
                "commission": commission,
                "deployed": deployed,
                "enable_ssh": enable_ssh,
                "skip_bmc_config": skip_bmc_config,
                "skip_networking": skip_networking,
                "skip_storage": skip_storage,
                "commissioning_scripts": commissioning_scripts,
                "is_dpu": is_dpu,
                "testing_scripts": testing_scripts,
            }.items()
            if v is not None
        }
        return await client.post(  # type: ignore[no-any-return]
            "/api/2.0/machines/", json=body
        )
