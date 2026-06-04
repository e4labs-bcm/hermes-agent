"""Reusable service boundary for Agent Builder local backend requests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.control_plane.models import IncomingMessage
from agent_builder.runtime.hermes_adapter import HermesRuntimeAdapter
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway


class AgentBuilderService:
    """Orchestrate identity, capability, gateway, runtime, and audit for one turn."""

    def __init__(self, audit_path: str | Path | None = None) -> None:
        if audit_path is None:
            audit_path = Path(tempfile.gettempdir()) / "agent_builder_mvp_tool_events.jsonl"
        self.audit = JsonlAuditLog(audit_path)
        self.identity_resolver = DemoIdentityResolver()
        self.capability_resolver = DemoCapabilityResolver()
        self.gateway = ToolGateway(self.audit)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("mode", "contract")
        if mode not in {"contract", "live_safe"}:
            return {"status": "error", "error": "unsupported_mode"}
        if mode == "live_safe" and os.getenv("AGENT_BUILDER_LIVE_SAFE") != "1":
            return {
                "status": "error",
                "error": "live_safe_requires_explicit_env_gate",
                "detail": "Set AGENT_BUILDER_LIVE_SAFE=1 only after explicit user approval.",
            }

        incoming = IncomingMessage(
            tenant_id=payload["tenant_id"],
            workspace_id=payload["workspace_id"],
            agent_instance_id=payload["agent_instance_id"],
            external_user_ref=payload["external_user_ref"],
            channel=payload["channel"],
            thread_id=payload.get("thread_id"),
            message=payload["message"],
        )
        context = self.identity_resolver.resolve_turn(incoming)
        surface = self.capability_resolver.resolve(context)

        customer_result = self.gateway.call(
            context=context,
            surface=surface,
            tool_name="erp_get_customer",
            args={"customer_name": "ACME"},
            tool_call_id="service_customer_001",
        )
        orders_result = self.gateway.call(
            context=context,
            surface=surface,
            tool_name="erp_list_orders",
            args={"customer_id": customer_result["customer"]["id"], "status": "open"},
            tool_call_id="service_orders_001",
        )

        if mode == "contract":
            adapter_result = HermesRuntimeAdapter(mode="contract").run_contract(
                context=context,
                surface=surface,
                message=incoming.message,
            )
            answer = f"Contrato validado; {len(orders_result['orders'])} pedidos em aberto."
        else:
            adapter_result = HermesRuntimeAdapter(mode="live_safe").run_live_safe(
                context=context,
                surface=surface,
                gateway=self.gateway,
                message=incoming.message,
            )
            answer = adapter_result["response"]

        session_events = [
            event
            for event in self.audit.read_events()
            if event.get("session_key") == context.session_key
        ]
        return {
            "status": "ok",
            "mode": mode,
            "session_key": context.session_key,
            "policy_snapshot_id": surface.policy_snapshot_id,
            "schema_digest": surface.schema_digest,
            "allowed_toolsets": list(surface.allowed_toolsets),
            "allowed_tools": list(surface.allowed_tools),
            "tool_events": [event["event_id"] for event in session_events],
            "audit_event_path": str(self.audit.path),
            "answer": answer,
            "runtime_metadata": adapter_result["runtime_metadata"],
        }
