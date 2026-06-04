import pytest

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.runtime.hermes_adapter import HermesRuntimeAdapter
from tests.agent_builder.test_identity import make_message


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


def test_live_mode_build_spec_does_not_call_external_llm():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="live")

    spec = adapter.build_live_agent_kwargs(context=context, surface=surface)

    assert spec["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert spec["skip_context_files"] is True
    assert spec["skip_memory"] is True
    assert spec["platform"] == "agent_builder"
    assert spec["session_id"] == context.session_key
