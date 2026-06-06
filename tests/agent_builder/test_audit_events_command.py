import json
import subprocess
import sys

from agent_builder.api.service import AgentBuilderService


def test_audit_events_command_returns_session_events(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    run_response = AgentBuilderService(audit_path=audit_path).run(
        {
            "tenant_id": "tenant_demo",
            "workspace_id": "workspace_demo",
            "agent_instance_id": "agent_sales_assistant",
            "external_user_ref": "whatsapp:+551****9999",
            "channel": "whatsapp",
            "thread_id": None,
            "message": "Quais pedidos o cliente ACME tem em aberto?",
            "mode": "contract",
        }
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            str(audit_path),
            "--session-key",
            run_response["session_key"],
            "--run-id",
            run_response["run_id"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["session_key"] == run_response["session_key"]
    assert payload["run_id"] == run_response["run_id"]
    assert len(payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in payload["events"])
