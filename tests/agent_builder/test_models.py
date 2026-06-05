import pytest

from agent_builder.control_plane.models import (
    CapabilitySurface,
    IncomingMessage,
    ResolvedIdentity,
    ResolvedTurnContext,
    ToolEvent,
    build_session_key,
    build_memory_scope,
)


def test_incoming_message_requires_business_routing_fields():
    message = IncomingMessage(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        external_user_ref="whatsapp:+5511999999999",
        channel="whatsapp",
        thread_id=None,
        message="Quais pedidos estão em aberto?",
    )

    assert message.tenant_id == "tenant_demo"
    assert message.thread_or_default == "default"


def test_missing_required_model_fields_raise_type_error():
    with pytest.raises(TypeError):
        IncomingMessage(tenant_id="tenant_demo")


def test_session_key_generation_includes_enterprise_boundaries():
    key = build_session_key(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        internal_user_id="user_001",
        channel="whatsapp",
        thread_id=None,
    )

    assert key.startswith("ab_session:sha256:")


def test_memory_scope_generation_is_user_agent_and_session_scoped():
    scope = build_memory_scope(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        internal_user_id="user_001",
        scope="session",
    )

    assert scope.startswith("ab_memory:sha256:")


def test_all_boundary_models_construct_with_expected_fields():
    identity = ResolvedIdentity(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        external_user_ref="whatsapp:+5511999999999",
        internal_user_id="user_001",
    )
    context = ResolvedTurnContext(
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        internal_user_id="user_001",
        session_key="tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default",
        memory_scope="tenant_demo/workspace_demo/agent_sales_assistant/user_001/session",
        policy_snapshot_id="policy_demo_readonly_v1",
        channel="whatsapp",
        thread_id=None,
    )
    surface = CapabilitySurface(
        policy_snapshot_id="policy_demo_readonly_v1",
        allowed_toolsets=("agent_builder_erp_read",),
        allowed_tools=("erp_get_customer", "erp_list_orders"),
        blocked_tools=("terminal", "browser"),
        approval_required_tools=(),
        schema_digest="sha256:test",
    )
    event = ToolEvent(
        event_id="evt_001",
        tenant_id="tenant_demo",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        internal_user_id="user_001",
        session_key=context.session_key,
        tool_call_id="call_001",
        tool_name="erp_list_orders",
        policy_snapshot_id="policy_demo_readonly_v1",
        schema_digest="sha256:test",
        args_redacted={},
        result_redacted={},
        status="executed",
        side_effect_committed=False,
        external_ref=None,
        duration_ms=0,
        created_at="2026-01-01T00:00:00Z",
    )

    assert identity.internal_user_id == "user_001"
    assert context.thread_or_default == "default"
    assert surface.allows_tool("erp_list_orders")
    assert not surface.allows_tool("terminal")
    assert event.side_effect_committed is False
