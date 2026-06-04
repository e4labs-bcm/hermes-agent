"""JSON stdin/stdout runner for Agent Builder backend requests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agent_builder.api.service import AgentBuilderService


def run_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    audit_path = payload.pop("audit_path", None)
    service = AgentBuilderService(audit_path=Path(audit_path) if audit_path else None)
    return service.run(payload)


def main() -> None:
    payload = json.loads(sys.stdin.read())
    response = run_from_payload(payload)
    print(json.dumps(response, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
