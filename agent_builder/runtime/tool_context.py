"""Scoped runtime context for Agent Builder Hermes tool calls."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


agent_builder_tool_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "agent_builder_tool_context",
    default=None,
)
