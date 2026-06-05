import json

import tools.agent_builder_erp_read_tool  # noqa: F401 - forces registry side effect
from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.runtime.tool_context import agent_builder_tool_context
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway
from tests.agent_builder.test_identity import make_message
from tools.registry import registry
from toolsets import resolve_toolset


def make_runtime_tool_context(tmp_path):
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    audit = JsonlAuditLog(tmp_path / "events.jsonl")
    return {
        "context": context,
        "surface": surface,
        "gateway": ToolGateway(audit),
        "audit": audit,
    }


def test_agent_builder_erp_tools_are_registered():
    entry = registry.get_entry("erp_get_customer")
    assert entry is not None
    assert entry.toolset == "agent_builder_erp_read"

    names = registry.get_tool_names_for_toolset("agent_builder_erp_read")
    assert names == ["erp_get_customer", "erp_list_orders"]


def test_erp_get_customer_handler_uses_gateway_and_audits(tmp_path):
    runtime_context = make_runtime_tool_context(tmp_path)
    token = agent_builder_tool_context.set(runtime_context)
    try:
        entry = registry.get_entry("erp_get_customer")
        payload = json.loads(entry.handler({"customer_name": "ACME"}))
    finally:
        agent_builder_tool_context.reset(token)

    assert payload["customer"]["id"] == "cust_acme"
    events = runtime_context["audit"].read_events()
    assert len(events) == 1
    assert events[0]["tool_name"] == "erp_get_customer"
    assert events[0]["side_effect_committed"] is False


def test_erp_tool_handler_fails_closed_without_runtime_context():
    entry = registry.get_entry("erp_get_customer")
    payload = json.loads(entry.handler({"customer_name": "ACME"}))

    assert payload["error"] == "agent_builder_runtime_context_required"


def test_agent_builder_erp_read_toolset_resolves_only_erp_tools():
    assert resolve_toolset("agent_builder_erp_read") == ["erp_get_customer", "erp_list_orders"]
