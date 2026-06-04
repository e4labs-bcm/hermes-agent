import json
import subprocess
import sys


def test_local_smoke_command_exits_zero_and_prints_contract_markers():
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.local_smoke"],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["session_key"] == "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default"
    assert payload["allowed_toolsets"] == ["agent_builder_erp_read"]
    assert payload["forbidden_toolsets_absent"] is True
    assert payload["audit_event_count"] >= 1
    assert payload["adapter_mode"] == "contract"
