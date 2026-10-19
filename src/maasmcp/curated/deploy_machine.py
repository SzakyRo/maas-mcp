"""deploy_machine: commission if needed, set OS, deploy, wait."""

from __future__ import annotations

import base64
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_op_path, machine_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.machines import MachineRecord
from maasmcp.curated._storage_paths import validate_system_id
from maasmcp.curated.wait_for_state import WaitForStateTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError

# Statuses that mean the machine needs to be commissioned before deploy.
# MAAS returns Title-case status_name strings; comparing against UPPER-case
# would never match real MAAS values.
_NEEDS_COMMISSION_STATUSES = frozenset({"New", "Ready"})
# commissioning_status_name values that indicate the machine has been
# commissioned (Title-case from MAAS 3.x).
_COMMISSIONED_STATUSES = frozenset({"Passed", "Warning", "Skipped"})
# Statuses that must REFUSE deploy, regardless of what a re-commission
# would do. Deploying onto a machine in a known-bad state can corrupt the
# install or the box — the caller must explicitly re-commission or
# otherwise recover before retrying. MAAS Title-cases failure states, so
# these are Title-case strings (not the integer status enum).
_REFUSE_DEPLOY_STATUSES = frozenset(
    {"Failed commissioning", "Failed deployment", "Failed testing", "Broken"}
)


class DeployMachineTool:
    name = "deploy_machine"
    description = (
        "Deploy an operating system to a machine. "
        "Use this instead of separate commission + deploy calls; it commissions "
        "first when the machine is New or Ready without a successful commissioning "
        "status, then triggers deployment and waits for completion. "
        "Returns a status dict with fields such as system_id, status_name, and "
        "power_state. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — writes a new OS image and may overwrite any prior install; "
        "must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        distro: Annotated[
            str, Field(description="OS/distro series to deploy (e.g. 'ubuntu/jammy').")
        ],
        user_data: Annotated[
            str | None,
            Field(
                description="Cloud-init user-data script or payload (plain text). MAAS expects "
                "base64 on the wire; this tool encodes the plain text for you before sending."
            ),
        ] = None,
        hwe_kernel: Annotated[
            str | None, Field(description="Hardware-enablement kernel to use.")
        ] = None,
        timeout_seconds: Annotated[
            int, Field(description="Maximum seconds to wait for deployment to finish.")
        ] = 1800,
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> MachineRecord:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if confirm is not True:
            raise ValueError(
                "deploy_machine is destructive (writes a new OS image, may "
                "commission first, overwrites any prior install); pass "
                f"confirm=True to proceed. Affected: system_id={system_id}, "
                f"hostname={hostname}, distro={distro}"
            )
        # Pre-flight: ensure the machine has been commissioned.
        machine = await client.get(machine_path(system_id))
        status = ""
        if isinstance(machine, dict):
            status = str(machine.get("status_name", ""))
            # commissioning_status_name is the Title-case string ("Passed",
            # "Warning", "Skipped"); commissioning_status (the integer enum)
            # is wrong to read here — it would always compare unequal.
            commission_status = str(machine.get("commissioning_status_name", ""))
            if (
                status in _NEEDS_COMMISSION_STATUSES
                and commission_status not in _COMMISSIONED_STATUSES
            ):
                await client.post(machine_op_path(system_id, "op-commission"))
                result = await WaitForStateTool().run(
                    client,
                    system_id=system_id,
                    # MAAS Title-cases failure states ("Failed commissioning",
                    # "Failed deployment") — there is no bare "Failed" value,
                    # so listing one would never match and we'd hang until
                    # timeout instead of failing fast.
                    target_states=["Ready", "Failed commissioning"],
                    timeout_seconds=timeout_seconds,
                )
                # Refuse to deploy if commissioning failed — the machine is
                # in an unknown hardware/OS state and deployment will likely
                # fail or, worse, corrupt the box.
                if str(result.get("status_name", "")).startswith("Failed"):
                    raise MCPUpstreamError(
                        f"commissioning failed for {system_id}; refusing to deploy "
                        f"(status {result.get('status_name')!r})",
                        status_code=0,
                        url=machine_op_path(system_id, "op-commission"),
                    )
                # Re-read status after the commission attempt so the refusal
                # check below sees the post-commission state, not the stale
                # pre-commission one.
                status = str(result.get("status_name", ""))

        # Explicit refusal: MAAS Title-case failure states ("Failed
        # commissioning", "Failed deployment", "Broken") MUST NOT silently
        # fall through to op-deploy. Without this, a Failed-commissioning
        # machine skips the commission branch above (its status is not in
        # _NEEDS_COMMISSION_STATUSES) and deploys onto a known-bad
        # hardware state. The caller must explicitly re-commission or
        # otherwise recover the machine before deploy will proceed.
        if status in _REFUSE_DEPLOY_STATUSES:
            raise MCPUpstreamError(
                f"refusing to deploy to {system_id} (status {status!r}); "
                "re-commission or otherwise recover the machine before retrying",
                status_code=0,
                url=machine_path(system_id),
            )

        body: dict[str, Any] = {
            "distro_series": distro,
        }
        if user_data:
            # Doc: user_data is a base64-encoded blob. Passing raw text would
            # land as undecodable user-data on the machine, so encode here.
            body["user_data"] = base64.b64encode(user_data.encode()).decode()
        if hwe_kernel:
            body["hwe_kernel"] = hwe_kernel
        await client.post(machine_op_path(system_id, "op-deploy"), json=body)
        result = await WaitForStateTool().run(
            client,
            system_id=system_id,
            target_states=["Deployed", "Failed deployment"],
            timeout_seconds=timeout_seconds,
        )
        if str(result.get("status_name", "")).startswith("Failed"):
            raise MCPUpstreamError(
                f"deployment failed for {system_id} (status {result.get('status_name')!r})",
                status_code=0,
                url=machine_op_path(system_id, "op-deploy"),
            )
        return result
