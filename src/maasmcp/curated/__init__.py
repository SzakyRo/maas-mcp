"""Hand-written MCP tools — the entire exposed MAAS surface.

Each tool is a small class (``name``, ``description``, ``run``, ``register``)
in its own module; :func:`register_curated` wires them all onto the shared
:class:`~mcp.server.mcpserver.MCPServer` instance built in :mod:`maasmcp.registry`.
"""

from maasmcp.curated._common import register_curated

__all__ = ["register_curated"]
