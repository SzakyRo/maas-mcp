"""Tests for the binding-layer wrapper guard rails."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from maasmcp.maas.binding import _make_wrapper
from maasmcp.maas.errors import MCPUpstreamError


def _zero_param_fn() -> None:  # pragma: no cover - only used as a bad input
    return None


def test_make_wrapper_rejects_zero_param_fn_cleanly() -> None:
    """Regression: the not-shaped-as-a-tool error path used to IndexError on
    params[0] for zero-parameter functions."""
    with pytest.raises(ValueError, match="<none>"):
        _make_wrapper(_zero_param_fn, lambda: None)


def test_make_wrapper_rejects_non_client_first_param() -> None:
    async def fn(not_client: str) -> None:
        return None

    with pytest.raises(ValueError, match="not_client"):
        _make_wrapper(fn, lambda: None)


def test_wrapper_converts_maas_error_to_tool_error_with_detail() -> None:
    """Agents must see actionable upstream messages, not opaque
    "Error executing tool" failures."""

    async def fn(client: object) -> None:
        raise MCPUpstreamError(
            "upstream 400",
            status_code=400,
            url="/machines/",
            detail="hostname: Already exists",
        )

    async def _run() -> None:
        wrapper = _make_wrapper(fn, lambda: "client")
        with pytest.raises(ToolError, match="hostname: Already exists"):
            await wrapper()

    import asyncio

    asyncio.run(_run())


def test_wrapper_converts_value_error_to_tool_error() -> None:
    async def fn(client: object) -> None:
        raise ValueError("confirm=True required")

    async def _run() -> None:
        wrapper = _make_wrapper(fn, lambda: "client")
        with pytest.raises(ToolError, match="confirm=True required"):
            await wrapper()

    import asyncio

    asyncio.run(_run())


def test_rebind_preserves_structured_output_decision() -> None:
    """The rebind pass must not undo per-tool structured_output choices.

    TypedDict-returning tools register unstructured (output_schema None);
    BaseModel-returning tools keep their schema. If rebind_all re-attempted
    schema creation for Unstructured tools, the "Cannot create schema"
    warning would fire twice per tool at startup.
    """
    from maasmcp.registry import mcp

    by_name = {t.name: t for t in mcp._tool_manager.list_tools()}
    # Unstructured: TypedDict returns cannot become pydantic output models.
    assert by_name["list_machines"].output_schema is None
    assert by_name["zones_list"].output_schema is None
    # Structured: BaseModel returns keep their output schema.
    assert by_name["tools_index"].output_schema is not None
    assert by_name["power_status"].output_schema is not None
