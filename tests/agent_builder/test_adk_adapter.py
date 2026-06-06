from agent_builder.api.adk_adapter import run_adk_runtime_request


def _payload(**overrides):
    payload = {
        "adk_run_id": "adk_run_001",
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "surface": {
            "allowed_toolsets": ["agent_builder_erp_read"],
            "allowed_tools": ["erp_get_customer", "erp_list_orders"],
            "policy_snapshot_id": "policy_demo_readonly_v1",
        },
    }
    payload.update(overrides)
    return payload


def test_adk_runtime_request_returns_adk_and_hermes_run_ids(tmp_path):
    response = run_adk_runtime_request(_payload(audit_path=str(tmp_path / "events.jsonl")))

    assert response["status"] == "ok"
    assert response["adk_run_id"] == "adk_run_001"
    assert response["hermes_run_id"].startswith("run_")
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]
    assert response["allowed_tools"] == ["erp_get_customer", "erp_list_orders"]
    assert response["tool_events"]


def test_adk_runtime_request_rejects_extra_tool_proposal(tmp_path):
    payload = _payload(audit_path=str(tmp_path / "events.jsonl"))
    payload["surface"]["allowed_tools"].append("terminal")

    response = run_adk_runtime_request(payload)

    assert response["status"] == "error"
    assert response["error"] == "adk_surface_mismatch"
    assert response["field"] == "surface.allowed_tools"
