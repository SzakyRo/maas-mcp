"""maasmcp: MCP server exposing Canonical MAAS to LLM agents."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("maasmcp")
except importlib.metadata.PackageNotFoundError:  # running from an uninstalled checkout
    __version__ = "0.0.0+not-installed"
