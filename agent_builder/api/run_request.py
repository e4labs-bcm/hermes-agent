"""JSON stdin/stdout runner for Agent Builder backend requests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agent_builder.api.service import AgentBuilderService


def run_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "error", "error": "invalid_request", "field": "payload", "reason": "object_required"}
    payload = dict(payload)
    audit_path = payload.pop("audit_path", None)
    service = AgentBuilderService(audit_path=Path(audit_path) if audit_path else None)
    return service.run(payload)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        response = {"status": "error", "error": "invalid_json", "detail": str(exc)}
    else:
        response = run_from_payload(payload)
    print(json.dumps(response, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
