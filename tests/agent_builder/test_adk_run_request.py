import json
import subprocess
import sys


def test_adk_run_request_accepts_json_stdin(tmp_path):
    payload = {
        "adk_run_id": "adk_run_cli_001",
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

    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.adk_run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "ok"
    assert response["adk_run_id"] == "adk_run_cli_001"
    assert response["hermes_run_id"].startswith("run_")
