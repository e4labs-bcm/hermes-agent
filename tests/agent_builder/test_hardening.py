import json
import os
import subprocess
import sys
import types

import pytest

from agent_builder.api.service import AgentBuilderService
from agent_builder.control_plane.capability import DemoCapabilityResolver, PolicyDenied
from agent_builder.control_plane.identity import DemoIdentityResolver, IdentityDenied
from agent_builder.control_plane.models import build_memory_scope, build_session_key
from agent_builder.runtime.tool_context import agent_builder_tool_context
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway
from model_tools import get_tool_definitions
from tests.agent_builder.test_identity import make_message
from tools.registry import registry
import tools.agent_builder_erp_read_tool  # noqa: F401


def valid_payload(**overrides):
    payload = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
    }
    payload.update(overrides)
    return payload


def test_service_rejects_missing_required_fields_as_json_error(tmp_path):
    response = AgentBuilderService(audit_path=tmp_path / "events.jsonl").run({"mode": "contract"})

    assert response["status"] == "error"
    assert response["error"] == "invalid_request"
    assert response["field"] == "tenant_id"


def test_run_request_returns_json_error_for_invalid_json():
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input="{not json",
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "error"
    assert payload["error"] == "invalid_json"


@pytest.mark.parametrize("field", ["tenant_id", "workspace_id", "agent_instance_id", "channel", "thread_id"])
def test_service_rejects_scope_delimiters_in_safe_identifier_fields(tmp_path, field):
    response = AgentBuilderService(audit_path=tmp_path / "events.jsonl").run(
        valid_payload(**{field: "bad:value/with-delimiter"})
    )

    assert response["status"] == "error"
    assert response["error"] == "invalid_request"
    assert response["field"] == field


def test_session_key_and_memory_scope_are_collision_resistant():
    first = build_session_key(
        tenant_id="a",
        workspace_id="b:c",
        agent_instance_id="d",
        internal_user_id="e",
        channel="f",
        thread_id="g",
    )
    second = build_session_key(
        tenant_id="a:b",
        workspace_id="c",
        agent_instance_id="d",
        internal_user_id="e",
        channel="f",
        thread_id="g",
    )
    assert first != second
    assert first.startswith("ab_session:sha256:")

    first_memory = build_memory_scope(
        tenant_id="a",
        workspace_id="b/c",
        agent_instance_id="d",
        internal_user_id="e",
    )
    second_memory = build_memory_scope(
        tenant_id="a/b",
        workspace_id="c",
        agent_instance_id="d",
        internal_user_id="e",
    )
    assert first_memory != second_memory
    assert first_memory.startswith("ab_memory:sha256:")


def test_unknown_external_user_is_denied():
    with pytest.raises(IdentityDenied):
        DemoIdentityResolver().resolve_identity(make_message(external_user_ref="whatsapp:+551****7777"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": "tenant_other"},
        {"workspace_id": "workspace_evil"},
        {"agent_instance_id": "agent_finance"},
    ],
)
def test_service_denies_unapproved_scope(tmp_path, overrides):
    response = AgentBuilderService(audit_path=tmp_path / "events.jsonl").run(valid_payload(**overrides))

    assert response["status"] == "error"
    assert response["error"] in {"identity_denied", "capability_denied"}


def test_capability_resolver_denies_unapproved_agent():
    context = DemoIdentityResolver().resolve_turn(make_message(agent_instance_id="agent_finance"))

    with pytest.raises(PolicyDenied):
        DemoCapabilityResolver().resolve(context)


def test_live_safe_tool_surface_ignores_kanban_env(monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_TASK", "review-probe")
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    kwargs = __import__("agent_builder.runtime.hermes_adapter", fromlist=["HermesRuntimeAdapter"]).HermesRuntimeAdapter(
        mode="live_safe"
    ).build_live_agent_kwargs(context=context, surface=surface)

    tools = sorted(
        tool["function"]["name"]
        for tool in get_tool_definitions(
            enabled_toolsets=kwargs["enabled_toolsets"],
            disabled_toolsets=kwargs["disabled_toolsets"],
            allowed_tools=kwargs["allowed_tools"],
            quiet_mode=True,
        )
    )
    assert tools == ["erp_get_customer", "erp_list_orders"]


def test_live_safe_tool_surface_intersects_allowed_tools_even_for_extra_registered_tool():
    registry.register(
        "evil_extra_tool",
        "agent_builder_erp_read",
        {
            "type": "function",
            "function": {
                "name": "evil_extra_tool",
                "description": "Should never be exposed by Agent Builder policy.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda _args, **_kwargs: "evil",
    )
    try:
        context = DemoIdentityResolver().resolve_turn(make_message())
        surface = DemoCapabilityResolver().resolve(context)
        kwargs = __import__("agent_builder.runtime.hermes_adapter", fromlist=["HermesRuntimeAdapter"]).HermesRuntimeAdapter(
            mode="live_safe"
        ).build_live_agent_kwargs(context=context, surface=surface)

        tools = sorted(
            tool["function"]["name"]
            for tool in get_tool_definitions(
                enabled_toolsets=kwargs["enabled_toolsets"],
                disabled_toolsets=kwargs["disabled_toolsets"],
                allowed_tools=kwargs["allowed_tools"],
                quiet_mode=True,
            )
        )
    finally:
        registry.deregister("evil_extra_tool")

    assert tools == ["erp_get_customer", "erp_list_orders"]


def test_default_tool_discovery_does_not_include_agent_builder_erp_tools():
    tools = {tool["function"]["name"] for tool in get_tool_definitions(enabled_toolsets=None, quiet_mode=True)}

    assert "erp_get_customer" not in tools
    assert "erp_list_orders" not in tools


def test_service_returns_only_events_for_current_run(tmp_path):
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")
    first = service.run(valid_payload())
    second = service.run(valid_payload())

    assert len(first["tool_events"]) == 2
    assert len(second["tool_events"]) == 2
    assert set(first["tool_events"]).isdisjoint(second["tool_events"])
    assert len(service.audit.events_for_session(first["session_key"])) == 4


def test_erp_tool_invalid_args_are_audited_as_failed(tmp_path):
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    audit = JsonlAuditLog(tmp_path / "events.jsonl")
    token = agent_builder_tool_context.set(
        {"context": context, "surface": surface, "gateway": ToolGateway(audit), "run_id": "run_test"}
    )
    try:
        payload = json.loads(registry.dispatch("erp_get_customer", {}))
    finally:
        agent_builder_tool_context.reset(token)

    assert payload["error"] == "invalid_tool_args"
    events = audit.read_events()
    assert len(events) == 1
    assert events[0]["status"] == "failed"
    assert events[0]["run_id"] == "run_test"


def test_gateway_non_object_args_are_failed_and_audited(tmp_path):
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    audit = JsonlAuditLog(tmp_path / "events.jsonl")
    gateway = ToolGateway(audit)

    result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_get_customer",
        args=None,
        tool_call_id="call_bad_args",
        run_id="run_bad_args",
    )

    assert result["error"] == "invalid_tool_args"
    events = audit.read_events()
    assert len(events) == 1
    assert events[0]["status"] == "failed"
    assert events[0]["run_id"] == "run_bad_args"
    assert events[0]["args_redacted"] == {"arg_type": "NoneType"}


def test_audit_events_command_returns_safe_projection(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    response = AgentBuilderService(audit_path=audit_path).run(valid_payload())
    AgentBuilderService(audit_path=audit_path).run(valid_payload())
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            str(audit_path),
            "--session-key",
            response["session_key"],
            "--run-id",
            response["run_id"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["run_id"] == response["run_id"]
    assert len(payload["events"]) == 2
    assert {event["run_id"] for event in payload["events"]} == {response["run_id"]}
    event = payload["events"][0]
    assert set(event) == {
        "event_id",
        "run_id",
        "tool_name",
        "status",
        "side_effect_committed",
        "duration_ms",
        "created_at",
        "policy_snapshot_id",
        "schema_digest",
    }
    assert "args_redacted" not in event
    assert "result_redacted" not in event


def test_live_safe_without_tool_calls_does_not_prefetch_erp_events(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_BUILDER_LIVE_SAFE", "1")

    class FakeAIAgent:
        def __init__(self, **_kwargs):
            pass

        def chat(self, _message):
            return "sem ferramentas"

    monkeypatch.setitem(sys.modules, "run_agent", types.SimpleNamespace(AIAgent=FakeAIAgent))
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")
    response = service.run(valid_payload(mode="live_safe"))

    assert response["status"] == "ok"
    assert response["tool_events"] == []
    assert service.audit.read_events() == []
