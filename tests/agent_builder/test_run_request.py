import json
import subprocess
import sys


def make_payload(tmp_path, mode="contract"):
    return {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": mode,
        "audit_path": str(tmp_path / "events.jsonl"),
    }


def test_run_request_accepts_json_stdin_and_returns_json(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(make_payload(tmp_path)),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "ok"
    assert response["mode"] == "contract"
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]


def test_run_request_rejects_live_safe_without_env_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_BUILDER_LIVE_SAFE", raising=False)
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(make_payload(tmp_path, mode="live_safe")),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "error"
    assert response["error"] == "live_safe_requires_explicit_env_gate"
