from agent_builder.api.service import AgentBuilderService


def make_payload(mode="contract"):
    return {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": mode,
    }


def test_service_run_contract_returns_backend_response_shape(tmp_path):
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")

    response = service.run(make_payload())

    assert response["status"] == "ok"
    assert response["mode"] == "contract"
    assert response["session_key"] == "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default"
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]
    assert response["allowed_tools"] == ["erp_get_customer", "erp_list_orders"]
    assert len(response["tool_events"]) == 2
    assert response["audit_event_path"].endswith("events.jsonl")
    assert "terminal" not in response["allowed_toolsets"]


def test_service_rejects_live_safe_without_env_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_BUILDER_LIVE_SAFE", raising=False)
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")

    response = service.run(make_payload(mode="live_safe"))

    assert response["status"] == "error"
    assert response["error"] == "live_safe_requires_explicit_env_gate"


def test_service_returns_controlled_error_when_gateway_blocks_customer_lookup(tmp_path):
    payload = make_payload()
    payload["tenant_id"] = "tenant_blocked"
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")

    response = service.run(payload)

    assert response["status"] == "error"
    assert response["error"] == "tool_gateway_blocked"
    assert response["tool_name"] == "erp_get_customer"
    assert response["gateway_error"] == "tenant_not_authorized"
    assert response["tool_events"]
