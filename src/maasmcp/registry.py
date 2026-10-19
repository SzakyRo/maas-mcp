"""Single hand-written registry of all MAAS-derived MCP tools.

Transport knobs belong to the transport, not the server, in MCP SDK v2:
``json_response=True`` is passed to ``streamable_http_app()`` in
:mod:`maasmcp.server` rather than to the ``MCPServer`` constructor. It
switches the streamable HTTP transport from SSE to plain JSON, which is
sufficient for request/response MCP clients like Claude Code.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from maasmcp.curated import register_curated
from maasmcp.maas.binding import rebind_all

mcp = MCPServer(name="maasmcp")

# Drop the ``client`` parameter from every registered tool's published
# signature. The SDK keeps ``Annotated[T, SkipJsonSchema()]`` as a
# *required* pydantic field, so without this rebind every tool call
# fails with ``client: Field required``. See maasmcp.maas.binding.
# Idempotent: re-running on a wrapper that already omits ``client`` is
# a no-op (the rebind guard skips it).
register_curated(mcp)
rebind_all(mcp)
