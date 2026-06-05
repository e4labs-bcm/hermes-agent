import sys
import types

import pytest

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.runtime.hermes_adapter import HermesRuntimeAdapter
from tests.agent_builder.test_identity import make_message
from toolsets import resolve_toolset


def make_context_and_surface():
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    return context, surface


def test_contract_mode_refuses_missing_capability_surface():
    context, _ = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="contract")

    with pytest.raises(ValueError, match="CapabilitySurface"):
        adapter.run_contract(context=context, surface=None, message="Oi")


def test_contract_mode_passes_only_allowed_toolsets():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="contract")

    result = adapter.run_contract(context=context, surface=surface, message="Oi")

    assert result["mode"] == "contract"
    assert result["would_create_agent_with"]["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert "terminal" not in result["would_create_agent_with"]["enabled_toolsets"]


def test_contract_mode_includes_enterprise_runtime_metadata():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="contract")

    result = adapter.run_contract(context=context, surface=surface, message="Oi")

    metadata = result["runtime_metadata"]
    assert metadata["tenant_id"] == "tenant_demo"
    assert metadata["session_key"] == context.session_key
    assert metadata["memory_scope"] == context.memory_scope
    assert metadata["policy_snapshot_id"] == surface.policy_snapshot_id


def test_live_safe_kwargs_keep_context_and_memory_controlled():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="live_safe")

    kwargs = adapter.build_live_agent_kwargs(context=context, surface=surface)

    assert kwargs["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert kwargs["skip_context_files"] is True
    assert kwargs["skip_memory"] is True
    assert kwargs["platform"] == "agent_builder"
    assert kwargs["session_id"] == context.session_key


def test_plain_live_mode_is_not_supported_for_agent_builder():
    with pytest.raises(ValueError, match="live_safe"):
        HermesRuntimeAdapter(mode="live")


def test_adapter_allowed_toolsets_resolve_to_readonly_erp_tools_only():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="contract")

    kwargs = adapter.build_live_agent_kwargs(context=context, surface=surface)
    resolved = []
    for toolset in kwargs["enabled_toolsets"]:
        resolved.extend(resolve_toolset(toolset))

    assert sorted(resolved) == ["erp_get_customer", "erp_list_orders"]
    assert "terminal" not in resolved
    assert "send_message" not in resolved


def test_run_live_safe_instantiates_aiagent_with_readonly_toolset(tmp_path, monkeypatch):
    context, surface = make_context_and_surface()
    captured = {}

    class FakeAIAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def chat(self, message):
            return "ACME tem 2 pedidos em aberto."

    fake_run_agent = types.SimpleNamespace(AIAgent=FakeAIAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    from agent_builder.tool_gateway.audit import JsonlAuditLog
    from agent_builder.tool_gateway.registry import ToolGateway

    gateway = ToolGateway(JsonlAuditLog(tmp_path / "events.jsonl"))
    result = HermesRuntimeAdapter(mode="live_safe").run_live_safe(
        context=context,
        surface=surface,
        gateway=gateway,
        message="Quais pedidos o cliente ACME tem em aberto?",
    )

    assert captured["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert result["mode"] == "live_safe"
    assert "2 pedidos" in result["response"]


def test_run_live_safe_resets_agent_builder_tool_context(tmp_path, monkeypatch):
    from agent_builder.runtime.tool_context import agent_builder_tool_context
    from agent_builder.tool_gateway.audit import JsonlAuditLog
    from agent_builder.tool_gateway.registry import ToolGateway

    context, surface = make_context_and_surface()

    class FakeAIAgent:
        def __init__(self, **_kwargs):
            pass

        def chat(self, _message):
            assert agent_builder_tool_context.get() is not None
            return "ok"

    fake_run_agent = types.SimpleNamespace(AIAgent=FakeAIAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    gateway = ToolGateway(JsonlAuditLog(tmp_path / "events.jsonl"))

    HermesRuntimeAdapter(mode="live_safe").run_live_safe(
        context=context,
        surface=surface,
        gateway=gateway,
        message="Oi",
    )

    assert agent_builder_tool_context.get() is None
