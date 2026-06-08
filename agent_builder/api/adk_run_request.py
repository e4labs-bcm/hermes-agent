"""stdin/stdout smoke entrypoint for ADK-shaped runtime calls."""

from __future__ import annotations

import json
import sys
from typing import Any

from agent_builder.api.adk_adapter import run_adk_runtime_request


def main() -> None:
    try:
        payload: Any = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": "invalid_json", "detail": str(exc)}, sort_keys=True))
        return
    print(json.dumps(run_adk_runtime_request(payload), sort_keys=True))


if __name__ == "__main__":
    main()
