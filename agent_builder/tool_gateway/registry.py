"""Product Tool Gateway for read-only Agent Builder ERP tools."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from agent_builder.control_plane.models import CapabilitySurface, ResolvedTurnContext, ToolEvent
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.erp_mock import erp_get_customer, erp_list_orders


AUTHORIZED_DEMO_TENANT = "tenant_demo"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ToolGateway:
    """Fail-closed gateway in front of product tools.

    Hermes built-in tools are not exposed here. The gateway only dispatches the
    product tools registered in this object and always writes a ToolEvent.
    """

    def __init__(self, audit_log: JsonlAuditLog) -> None:
        self.audit_log = audit_log
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "erp_get_customer": erp_get_customer,
            "erp_list_orders": erp_list_orders,
        }

    def call(
        self,
        *,
        context: ResolvedTurnContext,
        surface: CapabilitySurface,
        tool_name: str,
        args: dict[str, Any],
        tool_call_id: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        status = "executed"
        result: dict[str, Any]

        if context.tenant_id != AUTHORIZED_DEMO_TENANT:
            status = "blocked"
            result = {"error": "tenant_not_authorized"}
        elif not surface.allows_tool(tool_name) or tool_name not in self._tools:
            status = "blocked"
            result = {"error": "tool_not_allowed"}
        else:
            try:
                result = self._tools[tool_name](**args)
            except Exception as exc:  # pragma: no cover - defensive audit path
                status = "failed"
                result = {"error": "tool_failed", "detail": str(exc)}

        duration_ms = int((time.perf_counter() - started) * 1000)
        event = ToolEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            agent_instance_id=context.agent_instance_id,
            internal_user_id=context.internal_user_id,
            session_key=context.session_key,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            policy_snapshot_id=surface.policy_snapshot_id,
            schema_digest=surface.schema_digest,
            args_redacted=dict(args),
            result_redacted=dict(result),
            status=status,  # type: ignore[arg-type]
            side_effect_committed=False,
            external_ref=None,
            duration_ms=duration_ms,
            created_at=_utc_now(),
        )
        self.audit_log.append(event)
        return result
