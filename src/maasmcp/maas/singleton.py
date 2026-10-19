"""Shared MaasClient held at module level for tool-call injection.

The MCP SDK 1.28.x has a quirk in :func:`func_metadata`: an
``Annotated[T, SkipJsonSchema()]`` parameter is hidden from the tool's JSON
schema but stays as a *required* pydantic field, so any tool call with
``arguments={}`` fails validation with ``client: Field required``.

The fix used here is to keep the ``client`` parameter on every tool body
(it's the cleanest signature for the writers) and at registration time
wrap each registered tool with a function that *doesn't* take ``client``
in its signature. The wrapper reads the shared client from
:func:`get_shared_client` at call time.

The shared client itself is built once during the MCP-server lifespan
startup in :mod:`maasmcp.server` and torn down on shutdown. Tools run
concurrently under uvicorn, so the client must be safe for concurrent
use — ``httpx.AsyncClient`` already is, so no extra locking is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maasmcp.maas.client import MaasClient

# Module-level slot for the shared client. Set during MCP-server lifespan
# startup; cleared during shutdown. Reads outside of a running server
# will see ``None`` and raise — that's the intended failure mode (calling
# tools without the server running is a bug).
_client: MaasClient | None = None


def set_shared_client(client: MaasClient | None) -> None:
    """Install or clear the shared client used by tool wrappers.

    Called from the MCP-server lifespan wrapper in ``maasmcp.server`` —
    once on startup with the constructed client, once on shutdown with
    ``None``.
    """
    global _client
    _client = client


def get_shared_client() -> MaasClient:
    """Return the currently-installed shared MaasClient.

    Raises:
        RuntimeError: if no client has been installed (server not
            running, or lifespan startup never executed).
    """
    if _client is None:
        raise RuntimeError(
            "shared MaasClient is not installed; the MCP-server lifespan "
            "must set it before any tool runs"
        )
    return _client


__all__ = ["get_shared_client", "set_shared_client"]
