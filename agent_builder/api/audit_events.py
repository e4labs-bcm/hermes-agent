"""Inspect Agent Builder audit events for a specific session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_builder.tool_gateway.audit import JsonlAuditLog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Agent Builder audit events")
    parser.add_argument("--audit-path", required=True)
    parser.add_argument("--session-key", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    events = JsonlAuditLog(Path(args.audit_path)).events_for_session(args.session_key)
    print(json.dumps({"session_key": args.session_key, "events": events}, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
