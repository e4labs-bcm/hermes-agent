"""Identity and enterprise session resolution for the Agent Builder MVP."""

from __future__ import annotations

import hashlib

from agent_builder.control_plane.models import (
    IncomingMessage,
    ResolvedIdentity,
    ResolvedTurnContext,
    build_memory_scope,
    build_session_key,
)


DEMO_POLICY_SNAPSHOT_ID = "policy_demo_readonly_v1"


class DemoIdentityResolver:
    """Deterministic resolver used by the local Agent Builder MVP.

    This is intentionally not an auth system. It is the smallest resolver that
    proves the product boundary: external channel refs become internal users
    before Hermes sees the turn.
    """

    def __init__(self, known_users: dict[tuple[str, str, str], str] | None = None) -> None:
        self._known_users = known_users or {
            ("tenant_demo", "workspace_demo", "whatsapp:+551****9999"): "user_001"
        }

    def resolve_identity(self, message: IncomingMessage) -> ResolvedIdentity:
        key = (message.tenant_id, message.workspace_id, message.external_user_ref)
        internal_user_id = self._known_users.get(key)
        if internal_user_id is None:
            digest = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:12]
            internal_user_id = f"user_{digest}"
        return ResolvedIdentity(
            tenant_id=message.tenant_id,
            workspace_id=message.workspace_id,
            external_user_ref=message.external_user_ref,
            internal_user_id=internal_user_id,
        )

    def resolve_turn(self, message: IncomingMessage) -> ResolvedTurnContext:
        identity = self.resolve_identity(message)
        session_key = build_session_key(
            tenant_id=message.tenant_id,
            workspace_id=message.workspace_id,
            agent_instance_id=message.agent_instance_id,
            internal_user_id=identity.internal_user_id,
            channel=message.channel,
            thread_id=message.thread_id,
        )
        memory_scope = build_memory_scope(
            tenant_id=message.tenant_id,
            workspace_id=message.workspace_id,
            agent_instance_id=message.agent_instance_id,
            internal_user_id=identity.internal_user_id,
            scope="session",
        )
        return ResolvedTurnContext(
            tenant_id=message.tenant_id,
            workspace_id=message.workspace_id,
            agent_instance_id=message.agent_instance_id,
            internal_user_id=identity.internal_user_id,
            session_key=session_key,
            memory_scope=memory_scope,
            policy_snapshot_id=DEMO_POLICY_SNAPSHOT_ID,
            channel=message.channel,
            thread_id=message.thread_id,
        )
