"""Post-process registered MCP tools to drop the ``client`` parameter.

Every tool in this project has the shape::

    async def tool(
        client: Annotated[MaasClient, SkipJsonSchema()],
        ...public args...
    ) -> ...:
        return await client.something(...)

``SkipJsonSchema`` keeps ``client`` out of the published JSON schema
(which is what we want — the LLM never sees it) but the MCP SDK keeps
it as a *required* pydantic field on the tool's argument model, so any
call with ``arguments={}`` would fail validation with
``client: Field required`` if we registered the raw function.

The fix is to swap ``tool.fn`` for a wrapper whose signature omits
``client`` and re-derive the tool's pydantic arg-model and JSON schema.
The wrapper pulls the shared :class:`MaasClient` from
:mod:`maasmcp.maas.singleton` at call time.

Implementation note: the wrapper is built with ``exec()`` in the
original tool module's globals so that any forward references declared
in the same file as the tool resolve cleanly during pydantic schema
generation. A plain closure would live in *this* module's globals,
where those types aren't visible.

This module is the single source of truth for the rebind;
:mod:`maasmcp.registry` calls :func:`rebind_all` at import time.
"""

from __future__ import annotations

import contextlib
import inspect
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import func_metadata

from maasmcp.maas.errors import MAASError
from maasmcp.maas.singleton import get_shared_client

# Parameter name every rebindable tool takes as its first positional
# argument. All tool modules use ``client``; if a tool ever renames it,
# this constant is the single place to update.
_CLIENT_PARAM = "client"

# The wrapper translates MAASError, ValueError, and RuntimeError into
# ToolError. MCP SDK v2 hides the message of unexpected exceptions from MCP
# clients ("Error executing tool X"), which would turn every actionable
# upstream error, confirm-gate/validation rejection, or the singleton's
# "shared MaasClient is not installed" RuntimeError (tool called before the
# lifespan ran) into an opaque failure. ToolError is the SDK's channel for
# visibly surfaced messages; unit tests calling ``run()`` directly still see
# the raw exception (the wrapper only exists on the registered copy).
_WRAPPER_SRC = (
    "async def wrapper(*args, **kwargs):\n"
    "    bound = new_sig.bind(*args, **kwargs)\n"
    "    bound.apply_defaults()\n"
    "    try:\n"
    "        return await fn(client_provider(), **bound.arguments)\n"
    "    except (ValueError, RuntimeError, MAASError) as exc:\n"
    "        raise ToolError(str(exc)) from exc\n"
)


def _validate_tool_signature(fn: Any) -> list[inspect.Parameter]:
    """Enforce the contract the wrapper splice depends on.

    Returns the tool's parameter list. Raises ValueError when the first
    parameter isn't ``client`` (rebind target missing) or when any parameter
    is ``*args``/``**kwargs`` — those would be splatted into the call as one
    mis-named argument and fail confusingly inside the SDK instead of here,
    next to the offending tool.
    """
    params = list(inspect.signature(fn).parameters.values())
    if not params or params[0].name != _CLIENT_PARAM:
        first = params[0].name if params else "<none>"
        raise ValueError(
            f"rebind_client_param: {fn.__qualname__} first parameter "
            f"is {first!r}, expected {_CLIENT_PARAM!r}"
        )
    for p in params:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                f"rebind_client_param: {fn.__qualname__} declares "
                f"{p.kind.description} {p.name!r}; tool signatures must use "
                "explicit parameters only"
            )
    return params


def _resolve_return_annotation(
    sig: inspect.Signature, fn: Any
) -> inspect.Signature:
    """Pre-resolve a string return annotation into the real type.

    On exec'd wrappers, pydantic builds the output model inside its own
    namespace, where a bare-string annotation like 'ToolsIndexResponse'
    doesn't resolve (logged as "Cannot create schema" and the tool falls
    back to unstructured output). Parameters don't need this: arg_model gets
    an explicit model_rebuild with _types_namespace=fn.__globals__ below.
    """
    if not isinstance(sig.return_annotation, str):
        return sig
    # If resolution fails the string stays in place; func_metadata will log
    # and the tool falls back to unstructured output, as before.
    with contextlib.suppress(Exception):
        return sig.replace(return_annotation=eval(sig.return_annotation, fn.__globals__))
    return sig


def _exec_wrapper(fn: Any, new_sig: inspect.Signature, client_provider: Any) -> Any:
    """Build the wrapper in the original tool module's global namespace.

    ``exec`` in the tool module's globals (not this module's) so pydantic can
    resolve forward-referenced types declared alongside the tool — a plain
    closure would live in *this* module's globals, where those types aren't
    visible, and func_metadata would fail with "SomeType is not fully
    defined".
    """
    globals_ns = dict(fn.__globals__)
    globals_ns.update(
        new_sig=new_sig,
        fn=fn,
        client_provider=client_provider,
        ToolError=ToolError,
        MAASError=MAASError,
    )
    exec(_WRAPPER_SRC, globals_ns)
    wrapper = globals_ns["wrapper"]
    # Mirror identity attributes so reprs, tracebacks, and Starlette's
    # debug pages don't show ``wrapper`` instead of the real name.
    wrapper.__signature__ = new_sig
    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    wrapper.__wrapped__ = fn
    return wrapper


def _make_wrapper(
    fn: Any,
    client_provider: Any,
) -> Any:
    """Return an async function that calls ``fn`` with ``client`` injected.

    The returned wrapper has the *same* signature as ``fn`` minus the
    first parameter (``client``), so the MCP SDK rebuilds its arg model
    without the hidden-but-required field.
    """
    params = _validate_tool_signature(fn)
    new_sig = inspect.signature(fn).replace(parameters=params[1:])
    new_sig = _resolve_return_annotation(new_sig, fn)
    return _exec_wrapper(fn, new_sig, client_provider)


def rebind_all(mcp: MCPServer) -> int:
    """Rebind every registered tool whose first param is ``client``.

    Walks :attr:`MCPServer._tool_manager._tools`, swapping ``tool.fn`` for
    a wrapper that hides ``client`` and re-deriving ``fn_metadata`` /
    ``parameters`` so the JSON schema published to MCP clients no longer
    has the orphan required field.

    Idempotent: a wrapper whose first parameter is no longer ``client``
    (because it was already rebound) is left alone.

    The walk goes through double-private SDK attributes, and this rebind is
    load-bearing — without it every tool call fails with
    ``client: Field required``. So instead of silently wrapping nothing on
    an SDK upgrade that renamed the attributes, this raises: a loud startup
    failure next to a pinned SDK beats 126 broken tools in production.

    Returns:
        The number of tools that were rebound.
    """
    tool_manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(tool_manager, "_tools", None)
    if not isinstance(tools, dict):
        raise RuntimeError(
            "MCP SDK internals changed: MCPServer._tool_manager._tools not found "
            "(or not a dict). The client-param rebind depends on it — adapt "
            "maas/binding.py before upgrading the `mcp` package."
        )
    rebound = 0
    for tool in tools.values():
        fn = tool.fn
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if not params or params[0].name != _CLIENT_PARAM:
            continue
        wrapper = _make_wrapper(fn, get_shared_client)
        # Preserve the structured-output decision made at registration:
        # tools whose return type couldn't be modeled (TypedDict schemas)
        # registered with output_schema None; re-attempting here would only
        # re-log the "Cannot create schema" warning, so keep them explicitly
        # unstructured.
        new_metadata = func_metadata(
            wrapper,
            skip_names=[],
            structured_output=None if tool.fn_metadata.output_schema is not None else False,
        )
        # The wrapper was exec'd in a *copy* of the tool module's globals,
        # so the new arg model's forward refs can't be resolved
        # automatically. Hand pydantic the original module's namespace
        # explicitly so ``model_json_schema`` and ``model_validate`` both
        # work.
        new_metadata.arg_model.model_rebuild(_types_namespace=fn.__globals__)
        tool.fn = wrapper
        tool.fn_metadata = new_metadata
        tool.parameters = new_metadata.arg_model.model_json_schema(by_alias=True)
        rebound += 1
    if tools and rebound == 0:
        raise RuntimeError(
            f"rebind_all rebound 0 of {len(tools)} registered tools — every tool "
            "is expected to take `client` as its first parameter; signature "
            "convention drift would otherwise disable the whole server at runtime."
        )
    return rebound


__all__ = ["rebind_all"]
