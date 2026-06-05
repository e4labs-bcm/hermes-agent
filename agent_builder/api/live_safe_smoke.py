"""Gated manual live-safe Agent Builder smoke command."""

from __future__ import annotations

import json
import os
import sys

from agent_builder.api.service import AgentBuilderService


def live_safe_payload() -> dict:
    return {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "live_safe",
    }


def main() -> None:
    if os.getenv("AGENT_BUILDER_LIVE_SAFE") != "1":
        print(
            "Refusing live-safe smoke. Set AGENT_BUILDER_LIVE_SAFE=1 only after explicit approval.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    response = AgentBuilderService().run(live_safe_payload())
    print(json.dumps(response, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
