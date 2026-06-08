import json
import subprocess
import sys


def _payload(tmp_path):
    return {
        "adk_run_id": "adk_run_integration_001",
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(tmp_path / "events.jsonl"),
        "surface": {
            "allowed_toolsets": ["agent_builder_erp_read"],
            "allowed_tools": ["erp_get_customer", "erp_list_orders"],
            "policy_snapshot_id": "policy_demo_readonly_v1",
        },
    }


def _run(payload):
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.adk_run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_adk_permitted_request_and_audit_projection(tmp_path):
    response = _run(_payload(tmp_path))

    assert response["status"] == "ok"
    assert response["tool_events"]

    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            response["audit_event_path"],
            "--session-key",
            response["session_key"],
            "--run-id",
            response["hermes_run_id"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    audit_payload = json.loads(audit.stdout)
    assert len(audit_payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in audit_payload["events"])


def test_adk_forbidden_tool_surface_is_denied_before_runtime(tmp_path):
    payload = _payload(tmp_path)
    payload["surface"]["allowed_tools"] = ["erp_get_customer", "erp_list_orders", "terminal"]

    response = _run(payload)

    assert response["status"] == "error"
    assert response["error"] == "adk_surface_mismatch"
