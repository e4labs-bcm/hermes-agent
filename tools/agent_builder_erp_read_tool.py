"""Hermes tool registrations for Agent Builder read-only ERP access."""

from __future__ import annotations

import json
import uuid
from typing import Any

from agent_builder.runtime.tool_context import agent_builder_tool_context
from tools.registry import registry


def _available() -> bool:
    return True


def _call_gateway(tool_name: str, args: dict[str, Any]) -> str:
    runtime_context = agent_builder_tool_context.get()
    if runtime_context is None:
        return json.dumps({"error": "agent_builder_runtime_context_required"})

    result = runtime_context["gateway"].call(
        context=runtime_context["context"],
        surface=runtime_context["surface"],
        tool_name=tool_name,
        args=args,
        tool_call_id=f"hermes_{uuid.uuid4().hex}",
        run_id=runtime_context.get("run_id"),
    )
    return json.dumps(result, ensure_ascii=False)


def _get_customer_handler(args, **_kwargs):
    return _call_gateway("erp_get_customer", dict(args or {}))


def _list_orders_handler(args, **_kwargs):
    return _call_gateway("erp_list_orders", dict(args or {}))


registry.register(
    name="erp_get_customer",
    toolset="agent_builder_erp_read",
    schema={
        "name": "erp_get_customer",
        "description": "Read-only lookup of a customer through the Agent Builder Tool Gateway.",
        "parameters": {
            "type": "object",
            "properties": {"customer_name": {"type": "string"}},
            "required": ["customer_name"],
            "additionalProperties": False,
        },
    },
    handler=_get_customer_handler,
    check_fn=_available,
    requires_env=[],
    description="Gateway-audited read-only Agent Builder ERP customer lookup",
    emoji="🏢",
)

registry.register(
    name="erp_list_orders",
    toolset="agent_builder_erp_read",
    schema={
        "name": "erp_list_orders",
        "description": "Read-only order listing through the Agent Builder Tool Gateway.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "status": {"type": "string", "default": "open"},
            },
            "required": ["customer_id"],
            "additionalProperties": False,
        },
    },
    handler=_list_orders_handler,
    check_fn=_available,
    requires_env=[],
    description="Gateway-audited read-only Agent Builder ERP order listing",
    emoji="📦",
)
