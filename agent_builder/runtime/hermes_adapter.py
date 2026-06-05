"""Hermes runtime adapter for the Agent Builder MVP.

The adapter keeps Hermes behind a product contract. Tests use contract mode so
no provider call is required, while live_safe mode can instantiate AIAgent with
an already-resolved capability surface and a scoped ToolGateway context.
"""

from __future__ import annotations

from typing import Any, Literal

from agent_builder.control_plane.models import CapabilitySurface, ResolvedTurnContext
from agent_builder.runtime.tool_context import agent_builder_tool_context
from agent_builder.tool_gateway.registry import ToolGateway

RuntimeMode = Literal["contract", "live_safe"]


class HermesRuntimeAdapter:
    def __init__(self, mode: RuntimeMode = "contract") -> None:
        if mode == "live":
            raise ValueError("plain live mode is not supported; use live_safe")
        if mode not in {"contract", "live_safe"}:
            raise ValueError(f"unsupported HermesRuntimeAdapter mode: {mode}")
        self.mode = mode

    def _require_surface(self, surface: CapabilitySurface | None) -> CapabilitySurface:
        if surface is None:
            raise ValueError("CapabilitySurface is required before invoking Hermes runtime")
        return surface

    def runtime_metadata(
        self, *, context: ResolvedTurnContext, surface: CapabilitySurface
    ) -> dict[str, Any]:
        return {
            "tenant_id": context.tenant_id,
            "workspace_id": context.workspace_id,
            "agent_instance_id": context.agent_instance_id,
            "internal_user_id": context.internal_user_id,
            "session_key": context.session_key,
            "memory_scope": context.memory_scope,
            "policy_snapshot_id": surface.policy_snapshot_id,
            "schema_digest": surface.schema_digest,
        }

    def build_live_agent_kwargs(
        self, *, context: ResolvedTurnContext, surface: CapabilitySurface | None
    ) -> dict[str, Any]:
        surface = self._require_surface(surface)
        from toolsets import get_all_toolsets

        disabled_toolsets = sorted(
            toolset for toolset in get_all_toolsets() if toolset not in surface.allowed_toolsets
        )
        return {
            "enabled_toolsets": list(surface.allowed_toolsets),
            "disabled_toolsets": disabled_toolsets,
            "allowed_tools": list(surface.allowed_tools),
            "skip_context_files": True,
            "skip_memory": True,
            "platform": "agent_builder",
            "session_id": context.session_key,
        }

    def run_contract(
        self,
        *,
        context: ResolvedTurnContext,
        surface: CapabilitySurface | None,
        message: str,
    ) -> dict[str, Any]:
        surface = self._require_surface(surface)
        agent_kwargs = self.build_live_agent_kwargs(context=context, surface=surface)
        return {
            "mode": "contract",
            "message": message,
            "would_create_agent_with": agent_kwargs,
            "runtime_metadata": self.runtime_metadata(context=context, surface=surface),
        }

    def run_live_safe(
        self,
        *,
        context: ResolvedTurnContext,
        surface: CapabilitySurface | None,
        gateway: ToolGateway,
        message: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Instantiate Hermes in explicitly gated live-safe mode.

        This path is intentionally kept out of normal unit tests except through
        a mocked AIAgent. Runtime-visible ERP tools receive only the scoped
        Agent Builder context and service-owned gateway/audit object.
        """

        surface = self._require_surface(surface)
        from run_agent import AIAgent  # Imported lazily to keep contract tests offline.

        agent = AIAgent(**self.build_live_agent_kwargs(context=context, surface=surface))
        token = agent_builder_tool_context.set(
            {"context": context, "surface": surface, "gateway": gateway, "run_id": run_id}
        )
        try:
            response = agent.chat(message)
        finally:
            agent_builder_tool_context.reset(token)
        return {
            "mode": "live_safe",
            "response": response,
            "runtime_metadata": self.runtime_metadata(context=context, surface=surface),
        }
