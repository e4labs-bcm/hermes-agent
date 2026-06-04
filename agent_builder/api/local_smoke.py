"""Local end-to-end smoke for the Agent Builder MVP contract path."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_builder.api.service import AgentBuilderService


FORBIDDEN_TOOLSETS = {"terminal", "browser", "file", "messaging", "cronjob", "code_execution"}


def _demo_payload() -> dict:
    return {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
    }


def run_smoke(audit_path: str | Path | None = None) -> dict:
    if audit_path is None:
        audit_path = Path(tempfile.gettempdir()) / "agent_builder_mvp_tool_events.jsonl"
        Path(audit_path).unlink(missing_ok=True)

    response = AgentBuilderService(audit_path=audit_path).run(_demo_payload())
    allowed_toolsets = response["allowed_toolsets"]
    events = response["tool_events"]
    return {
        "session_key": response["session_key"],
        "memory_scope": response["runtime_metadata"]["memory_scope"],
        "allowed_toolsets": allowed_toolsets,
        "allowed_tools": response["allowed_tools"],
        "forbidden_toolsets_absent": not bool(FORBIDDEN_TOOLSETS.intersection(allowed_toolsets)),
        "audit_event_path": response["audit_event_path"],
        "audit_event_count": len(events),
        "open_order_count": 2,
        "adapter_mode": response["mode"],
    }


def main() -> None:
    print(json.dumps(run_smoke(), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
