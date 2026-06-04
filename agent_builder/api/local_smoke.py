"""Local end-to-end smoke for the Agent Builder MVP contract path."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.control_plane.models import IncomingMessage
from agent_builder.runtime.hermes_adapter import HermesRuntimeAdapter
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway


FORBIDDEN_TOOLSETS = {"terminal", "browser", "file", "messaging", "cronjob", "code_execution"}


def run_smoke(audit_path: str | Path | None = None) -> dict:
    incoming = IncomingMessage(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        external_user_ref="whatsapp:+551****9999",
        channel="whatsapp",
        thread_id=None,
        message="Quais pedidos o cliente ACME tem em aberto?",
    )
    context = DemoIdentityResolver().resolve_turn(incoming)
    surface = DemoCapabilityResolver().resolve(context)

    if audit_path is None:
        audit_path = Path(tempfile.gettempdir()) / "agent_builder_mvp_tool_events.jsonl"
        Path(audit_path).unlink(missing_ok=True)
    audit = JsonlAuditLog(audit_path)
    gateway = ToolGateway(audit)

    customer_result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_get_customer",
        args={"customer_name": "ACME"},
        tool_call_id="smoke_customer_001",
    )
    customer_id = customer_result["customer"]["id"]
    orders_result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_list_orders",
        args={"customer_id": customer_id, "status": "open"},
        tool_call_id="smoke_orders_001",
    )

    adapter_result = HermesRuntimeAdapter(mode="contract").run_contract(
        context=context,
        surface=surface,
        message=incoming.message,
    )
    events = audit.read_events()
    allowed_toolsets = list(surface.allowed_toolsets)
    return {
        "session_key": context.session_key,
        "memory_scope": context.memory_scope,
        "allowed_toolsets": allowed_toolsets,
        "allowed_tools": list(surface.allowed_tools),
        "forbidden_toolsets_absent": not bool(FORBIDDEN_TOOLSETS.intersection(allowed_toolsets)),
        "audit_event_path": str(audit.path),
        "audit_event_count": len(events),
        "open_order_count": len(orders_result["orders"]),
        "adapter_mode": adapter_result["mode"],
    }


def main() -> None:
    print(json.dumps(run_smoke(), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
