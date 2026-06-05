"""Append-only JSONL audit log for Agent Builder ToolEvents."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from agent_builder.control_plane.models import ToolEvent


class JsonlAuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: ToolEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(event) if is_dataclass(event) else event
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def events_for_session(self, session_key: str) -> list[dict[str, Any]]:
        return [event for event in self.read_events() if event.get("session_key") == session_key]

    def _public_event(self, event: dict[str, Any]) -> dict[str, Any]:
        public_fields = (
            "event_id",
            "run_id",
            "tool_name",
            "status",
            "side_effect_committed",
            "duration_ms",
            "created_at",
            "policy_snapshot_id",
            "schema_digest",
        )
        return {field: event.get(field) for field in public_fields}

    def public_events_for_session(self, session_key: str) -> list[dict[str, Any]]:
        return [self._public_event(event) for event in self.events_for_session(session_key)]

    def public_events_for_run(self, session_key: str, run_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self.public_events_for_session(session_key)
            if event.get("run_id") == run_id
        ]
