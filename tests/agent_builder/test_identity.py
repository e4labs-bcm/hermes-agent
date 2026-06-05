import pytest

from agent_builder.control_plane.identity import DemoIdentityResolver, IdentityDenied
from agent_builder.control_plane.models import IncomingMessage


def make_message(**overrides):
    data = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos estão em aberto?",
    }
    data.update(overrides)
    return IncomingMessage(**data)


def test_same_external_user_maps_to_same_internal_user():
    resolver = DemoIdentityResolver()

    first = resolver.resolve_identity(make_message())
    second = resolver.resolve_identity(make_message(message="Outra pergunta"))

    assert first.internal_user_id == second.internal_user_id == "user_001"


def test_unknown_external_user_is_denied():
    resolver = DemoIdentityResolver()
    message = make_message(external_user_ref="whatsapp:+551****7777")

    with pytest.raises(IdentityDenied):
        resolver.resolve_identity(message)


def test_resolved_turn_context_contains_enterprise_session_key_and_memory_scope():
    resolver = DemoIdentityResolver()

    context = resolver.resolve_turn(make_message())

    assert context.session_key.startswith("ab_session:sha256:")
    assert context.memory_scope.startswith("ab_memory:sha256:")
    assert context.policy_snapshot_id == "policy_demo_readonly_v1"


def test_different_tenants_do_not_produce_same_session_key():
    first = DemoIdentityResolver().resolve_turn(make_message(tenant_id="tenant_demo"))

    from agent_builder.control_plane.models import build_session_key

    second = build_session_key(
        tenant_id="tenant_other",
        workspace_id="workspace_demo",
        agent_instance_id="agent_sales_assistant",
        internal_user_id="user_001",
        channel="whatsapp",
        thread_id=None,
    )

    assert first.session_key != second


def test_different_agent_instances_do_not_produce_same_session_key():
    resolver = DemoIdentityResolver()

    first = resolver.resolve_turn(make_message(agent_instance_id="agent_sales_assistant"))
    second = resolver.resolve_turn(make_message(agent_instance_id="agent_finance_assistant"))

    assert first.session_key != second.session_key
