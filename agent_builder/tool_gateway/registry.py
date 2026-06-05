"""Product Tool Gateway for read-only Agent Builder ERP tools."""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from agent_builder.control_plane.capability import AUTHORIZED_DEMO_SCOPE
from agent_builder.control_plane.models import CapabilitySurface, ResolvedTurnContext, ToolEvent
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.erp_mock import erp_get_customer, erp_list_orders


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {"arg_type": type(args).__name__}
    if tool_name == "erp_list_orders":
        return {"customer_id": args.get("customer_id"), "status": args.get("status")}
    if tool_name == "erp_get_customer":
        digest = hashlib.sha256(str(args.get("customer_name", "")).encode("utf-8")).hexdigest()
        return {"customer_name_hash": f"sha256:{digest}"}
    return {"arg_keys": sorted(args)}


def _redact_result(result: dict[str, Any]) -> dict[str, Any]:
    if "error" in result:
        return {key: result[key] for key in ("error", "detail") if key in result}
    if "customer" in result:
        customer = result.get("customer") or {}
        return {"customer_id": customer.get("id")}
    if "orders" in result:
        return {"order_count": len(result.get("orders") or [])}
    return {"result_keys": sorted(result)}


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

    def _context_authorized(self, context: ResolvedTurnContext) -> bool:
        return all(getattr(context, field) == expected for field, expected in AUTHORIZED_DEMO_SCOPE.items())

    def _validate_args(self, tool_name: str, args: dict[str, Any]) -> str | None:
        if not isinstance(args, dict):
            return "args_must_be_object"
        if tool_name == "erp_get_customer":
            if set(args) != {"customer_name"}:
                return "unexpected_args"
            value = args.get("customer_name")
            if not isinstance(value, str) or not value.strip():
                return "missing_customer_name"
        elif tool_name == "erp_list_orders":
            if set(args) - {"customer_id", "status"}:
                return "unexpected_args"
            value = args.get("customer_id")
            if not isinstance(value, str) or not value.strip():
                return "missing_customer_id"
            status = args.get("status", "open")
            if not isinstance(status, str) or not status.strip():
                return "invalid_status"
        return None

    def call(
        self,
        *,
        context: ResolvedTurnContext,
        surface: CapabilitySurface,
        tool_name: str,
        args: Any,
        tool_call_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        status = "executed"
        result: dict[str, Any]

        if not self._context_authorized(context):
            status = "blocked"
            result = {"error": "context_not_authorized"}
        elif not surface.allows_tool(tool_name) or tool_name not in self._tools:
            status = "blocked"
            result = {"error": "tool_not_allowed"}
        else:
            arg_error = self._validate_args(tool_name, args)
            if arg_error:
                status = "failed"
                result = {"error": "invalid_tool_args", "detail": arg_error}
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
            run_id=run_id,
            args_redacted=_redact_args(tool_name, args),
            result_redacted=_redact_result(result),
            status=status,  # type: ignore[arg-type]
            side_effect_committed=False,
            external_ref=None,
            duration_ms=duration_ms,
            created_at=_utc_now(),
        )
        self.audit_log.append(event)
        return result
