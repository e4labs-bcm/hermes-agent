import json
import subprocess
import sys

from toolsets import resolve_toolset


def test_next_steps_contract_integration(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    request = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(audit_path),
    }

    run = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    response = json.loads(run.stdout)

    assert response["status"] == "ok"
    assert resolve_toolset("agent_builder_erp_read") == ["erp_get_customer", "erp_list_orders"]

    audit = subprocess.run(
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
    audit_payload = json.loads(audit.stdout)

    assert len(audit_payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in audit_payload["events"])
