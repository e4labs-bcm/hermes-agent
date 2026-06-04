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
