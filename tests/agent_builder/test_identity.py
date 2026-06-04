from agent_builder.control_plane.identity import DemoIdentityResolver
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


def test_unknown_external_user_gets_stable_hash_user_id():
    resolver = DemoIdentityResolver()
    message = make_message(external_user_ref="whatsapp:+551188887777")

    first = resolver.resolve_identity(message)
    second = resolver.resolve_identity(message)

    assert first.internal_user_id == second.internal_user_id
    assert first.internal_user_id.startswith("user_")


def test_resolved_turn_context_contains_enterprise_session_key_and_memory_scope():
    resolver = DemoIdentityResolver()

    context = resolver.resolve_turn(make_message())

    assert context.session_key == "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default"
    assert context.memory_scope == "tenant_demo/workspace_demo/agent_sales_assistant/user_001/session"
    assert context.policy_snapshot_id == "policy_demo_readonly_v1"


def test_different_tenants_do_not_produce_same_session_key():
    resolver = DemoIdentityResolver()

    first = resolver.resolve_turn(make_message(tenant_id="tenant_demo"))
    second = resolver.resolve_turn(make_message(tenant_id="tenant_other"))

    assert first.session_key != second.session_key


def test_different_agent_instances_do_not_produce_same_session_key():
    resolver = DemoIdentityResolver()

    first = resolver.resolve_turn(make_message(agent_instance_id="agent_sales_assistant"))
    second = resolver.resolve_turn(make_message(agent_instance_id="agent_finance_assistant"))

    assert first.session_key != second.session_key
