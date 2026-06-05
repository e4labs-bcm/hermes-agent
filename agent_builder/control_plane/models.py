"""Boundary models for the Agent Builder MVP control plane.

These models are intentionally small and stdlib-only. They define the contract
between a future product backend/control plane and Hermes as a private runtime.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal


ToolEventStatus = Literal["executed", "blocked", "failed"]


def _require_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value


def _normalize_thread(thread_id: str | None) -> str:
    return thread_id or "default"


def _scope_digest(prefix: str, payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def build_session_key(
    *,
    tenant_id: str,
    workspace_id: str,
    agent_instance_id: str,
    internal_user_id: str,
    channel: str,
    thread_id: str | None,
) -> str:
    """Build an enterprise-scoped session key.

    The key must include tenant, workspace, agent instance, user, channel, and
    thread/default so sessions never collapse across enterprise boundaries.
    """

    payload = {
        "tenant_id": _require_non_empty(tenant_id, "tenant_id"),
        "workspace_id": _require_non_empty(workspace_id, "workspace_id"),
        "agent_instance_id": _require_non_empty(agent_instance_id, "agent_instance_id"),
        "internal_user_id": _require_non_empty(internal_user_id, "internal_user_id"),
        "channel": _require_non_empty(channel, "channel"),
        "thread_id": _normalize_thread(thread_id),
    }
    return _scope_digest("ab_session", payload)


def build_memory_scope(
    *,
    tenant_id: str,
    workspace_id: str,
    agent_instance_id: str,
    internal_user_id: str,
    scope: str = "session",
) -> str:
    payload = {
        "tenant_id": _require_non_empty(tenant_id, "tenant_id"),
        "workspace_id": _require_non_empty(workspace_id, "workspace_id"),
        "agent_instance_id": _require_non_empty(agent_instance_id, "agent_instance_id"),
        "internal_user_id": _require_non_empty(internal_user_id, "internal_user_id"),
        "scope": _require_non_empty(scope, "scope"),
    }
    return _scope_digest("ab_memory", payload)


@dataclass(frozen=True)
class IncomingMessage:
    tenant_id: str
    workspace_id: str
    agent_instance_id: str
    external_user_ref: str
    channel: str
    thread_id: str | None
    message: str

    def __post_init__(self) -> None:
        _require_non_empty(self.tenant_id, "tenant_id")
        _require_non_empty(self.workspace_id, "workspace_id")
        _require_non_empty(self.agent_instance_id, "agent_instance_id")
        _require_non_empty(self.external_user_ref, "external_user_ref")
        _require_non_empty(self.channel, "channel")
        _require_non_empty(self.message, "message")

    @property
    def thread_or_default(self) -> str:
        return _normalize_thread(self.thread_id)


@dataclass(frozen=True)
class ResolvedIdentity:
    tenant_id: str
    workspace_id: str
    external_user_ref: str
    internal_user_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.tenant_id, "tenant_id")
        _require_non_empty(self.workspace_id, "workspace_id")
        _require_non_empty(self.external_user_ref, "external_user_ref")
        _require_non_empty(self.internal_user_id, "internal_user_id")


@dataclass(frozen=True)
class ResolvedTurnContext:
    tenant_id: str
    workspace_id: str
    agent_instance_id: str
    internal_user_id: str
    session_key: str
    memory_scope: str
    policy_snapshot_id: str
    channel: str
    thread_id: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "workspace_id",
            "agent_instance_id",
            "internal_user_id",
            "session_key",
            "memory_scope",
            "policy_snapshot_id",
            "channel",
        ):
            _require_non_empty(getattr(self, field_name), field_name)

    @property
    def thread_or_default(self) -> str:
        return _normalize_thread(self.thread_id)


@dataclass(frozen=True)
class CapabilitySurface:
    policy_snapshot_id: str
    allowed_toolsets: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    approval_required_tools: tuple[str, ...]
    schema_digest: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_snapshot_id, "policy_snapshot_id")
        _require_non_empty(self.schema_digest, "schema_digest")
        if not self.allowed_toolsets:
            raise ValueError("allowed_toolsets is required")
        if not self.allowed_tools:
            raise ValueError("allowed_tools is required")

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools and tool_name not in self.blocked_tools

    def allows_toolset(self, toolset: str) -> bool:
        return toolset in self.allowed_toolsets


@dataclass(frozen=True)
class ToolEvent:
    event_id: str
    tenant_id: str
    workspace_id: str
    agent_instance_id: str
    internal_user_id: str
    session_key: str
    tool_call_id: str
    tool_name: str
    policy_snapshot_id: str
    schema_digest: str
    run_id: str | None = None
    args_redacted: dict[str, Any] = field(default_factory=dict)
    result_redacted: dict[str, Any] = field(default_factory=dict)
    status: ToolEventStatus = "executed"
    side_effect_committed: bool = False
    external_ref: str | None = None
    duration_ms: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "tenant_id",
            "workspace_id",
            "agent_instance_id",
            "internal_user_id",
            "session_key",
            "tool_call_id",
            "tool_name",
            "policy_snapshot_id",
            "schema_digest",
            "created_at",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.status not in {"executed", "blocked", "failed"}:
            raise ValueError(f"invalid ToolEvent status: {self.status}")
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
