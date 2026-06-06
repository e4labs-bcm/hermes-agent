"""Capability resolution for the Agent Builder MVP."""

from __future__ import annotations

import hashlib
import json

from agent_builder.control_plane.models import CapabilitySurface, ResolvedTurnContext


READONLY_POLICY_SNAPSHOT_ID = "policy_demo_readonly_v1"
READONLY_TOOLSET = "agent_builder_erp_read"
READONLY_TOOLS = ("erp_get_customer", "erp_list_orders")
AUTHORIZED_DEMO_SCOPE = {
    "tenant_id": "tenant_demo",
    "workspace_id": "workspace_demo",
    "agent_instance_id": "agent_sales_assistant",
    "internal_user_id": "user_001",
}
DANGEROUS_HERMES_TOOLS = (
    "terminal",
    "browser",
    "file",
    "messaging",
    "cron",
    "write_file",
    "read_file",
    "patch",
    "send_message",
    "cronjob",
    "code_execution",
    "execute_code",
    "process",
)


class PolicyDenied(RuntimeError):
    """Raised when a tool call is outside the resolved surface."""


def _digest_policy(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DemoCapabilityResolver:
    """Fail-closed read-only resolver for the first Agent Builder MVP."""

    def _ensure_context_authorized(self, context: ResolvedTurnContext) -> None:
        for field, expected in AUTHORIZED_DEMO_SCOPE.items():
            if getattr(context, field) != expected:
                raise PolicyDenied(f"context is not authorized for demo policy: {field}")

    def resolve(self, context: ResolvedTurnContext) -> CapabilitySurface:
        self._ensure_context_authorized(context)
        policy_payload = {
            "tenant_id": context.tenant_id,
            "workspace_id": context.workspace_id,
            "agent_instance_id": context.agent_instance_id,
            "policy_snapshot_id": READONLY_POLICY_SNAPSHOT_ID,
            "allowed_toolsets": [READONLY_TOOLSET],
            "allowed_tools": list(READONLY_TOOLS),
            "blocked_tools": list(DANGEROUS_HERMES_TOOLS),
            "approval_required_tools": [],
        }
        return CapabilitySurface(
            policy_snapshot_id=READONLY_POLICY_SNAPSHOT_ID,
            allowed_toolsets=(READONLY_TOOLSET,),
            allowed_tools=READONLY_TOOLS,
            blocked_tools=DANGEROUS_HERMES_TOOLS,
            approval_required_tools=(),
            schema_digest=_digest_policy(policy_payload),
        )

    def ensure_tool_allowed(self, surface: CapabilitySurface, tool_name: str) -> None:
        if not surface.allows_tool(tool_name):
            raise PolicyDenied(f"tool is not allowed by capability surface: {tool_name}")
