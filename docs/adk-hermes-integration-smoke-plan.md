# ADK to Hermes Integration Smoke Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Prove a minimal ADK-controlled backend request can call Hermes as a private runtime through a governed Agent Builder surface, with allowed tools enforced server-side and audit evidence returned to ADK.

**Architecture:** ADK remains the control plane and trusted resolver. Hermes receives only a pre-resolved runtime request containing opaque workspace/user/agent/run context plus a server-derived capability surface. The existing `AgentBuilderService` remains the local runtime boundary; this plan adds a small ADK-shaped adapter, contract tests, denial cases, and a smoke command without exposing Hermes directly to the frontend.

**Tech Stack:** Python stdlib only, existing `agent_builder` package, existing `AgentBuilderService`, existing `JsonlAuditLog`, pytest with `-o 'addopts='`, GitHub PR workflow.

---

## Current state

Implemented and verified before this plan:

- `agent_builder/api/service.py` validates backend payloads fail-closed and creates a per-turn `run_id`.
- `agent_builder/api/request_validation.py` bounds identifiers, channel references, message length, and non-object payloads.
- `agent_builder/control_plane/models.py` uses opaque sha256-backed session and memory scope keys.
- `agent_builder/control_plane/identity.py` and `capability.py` only authorize the demo workspace/user/agent scope.
- `agent_builder/tool_gateway/registry.py` audits executed, blocked, failed, and invalid-args calls.
- `agent_builder/api/audit_events.py` exposes safe audit inspection and requires `run_id` for public projection.
- `tools/agent_builder_erp_read_tool.py` plus `toolsets.py` expose only `erp_get_customer` and `erp_list_orders` in `agent_builder_erp_read`.
- Final local gate already passed: `62 passed`, `compileall`, `local_smoke`, `run_request` contract, invalid JSON, and `git diff --check`.

## Primary gap

The current contract is Hermes-local. It proves the private runtime boundary, but it does not yet prove the ADK-facing integration shape: ADK-derived identity/capability fields, ADK run correlation, denied proposals, and safe audit result handoff back to ADK.

## Desired ADK contract

### ADK runtime request

```json
{
  "adk_run_id": "adk_run_001",
  "tenant_id": "tenant_demo",
  "workspace_id": "workspace_demo",
  "agent_instance_id": "agent_sales_assistant",
  "external_user_ref": "whatsapp:+551****9999",
  "channel": "whatsapp",
  "thread_id": null,
  "message": "Quais pedidos o cliente ACME tem em aberto?",
  "mode": "contract",
  "surface": {
    "allowed_toolsets": ["agent_builder_erp_read"],
    "allowed_tools": ["erp_get_customer", "erp_list_orders"],
    "policy_snapshot_id": "policy_demo_readonly_v1"
  }
}
```

### ADK runtime response

```json
{
  "status": "ok",
  "adk_run_id": "adk_run_001",
  "hermes_run_id": "run_...",
  "session_key": "ab_session:sha256:...",
  "allowed_toolsets": ["agent_builder_erp_read"],
  "allowed_tools": ["erp_get_customer", "erp_list_orders"],
  "tool_events": ["evt_..."],
  "audit_event_path": "/tmp/agent_builder_mvp_tool_events.jsonl",
  "answer": "Contrato validado; 2 pedidos em aberto."
}
```

## Non-goals

- No frontend-to-Hermes calls.
- No dynamic policy database yet; use an ADK-shaped local contract fixture.
- No write tools, approvals, pending actions, billing, RBAC UI, or customer admin UI.
- No live provider calls in normal tests.
- No terminal/browser/file/code/messaging/cron tools exposed to client agents.

## Authority boundaries

| Component | Owns | Does not own |
| --- | --- | --- |
| ADK adapter | Accepting ADK-shaped payload and translating it to the Hermes private runtime request | Identity database, long-term policy storage, frontend access |
| `AgentBuilderService` | Runtime orchestration, request validation, identity/capability resolution, gateway/audit handoff | Public HTTP serving or frontend routing |
| `DemoIdentityResolver` | Demo tenant/workspace/user mapping | Tool policy decisions |
| `DemoCapabilityResolver` | Server-derived allowed toolsets/tools and fail-closed scope authorization | Tool execution |
| `ToolGateway` | Product tool dispatch and canonical `ToolEvent` evidence | Assistant wording or ADK policy authoring |
| `JsonlAuditLog` | Local append/read event persistence | Authorization decisions |

---

## Phase 11 — ADK-shaped private runtime adapter

### Task 11.1: Add ADK payload validator

**Objective:** Validate an ADK-shaped runtime request and reject client-proposed tool surfaces that do not match the server-derived demo policy.

**Files:**
- Create: `agent_builder/api/adk_adapter.py`
- Test: `tests/agent_builder/test_adk_adapter.py`

**Step 1: Write failing tests**

```python
from agent_builder.api.adk_adapter import run_adk_runtime_request


def _payload(**overrides):
    payload = {
        "adk_run_id": "adk_run_001",
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "surface": {
            "allowed_toolsets": ["agent_builder_erp_read"],
            "allowed_tools": ["erp_get_customer", "erp_list_orders"],
            "policy_snapshot_id": "policy_demo_readonly_v1",
        },
    }
    payload.update(overrides)
    return payload


def test_adk_runtime_request_returns_adk_and_hermes_run_ids(tmp_path):
    response = run_adk_runtime_request(_payload(audit_path=str(tmp_path / "events.jsonl")))

    assert response["status"] == "ok"
    assert response["adk_run_id"] == "adk_run_001"
    assert response["hermes_run_id"].startswith("run_")
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]
    assert response["allowed_tools"] == ["erp_get_customer", "erp_list_orders"]
    assert response["tool_events"]


def test_adk_runtime_request_rejects_extra_tool_proposal(tmp_path):
    payload = _payload(audit_path=str(tmp_path / "events.jsonl"))
    payload["surface"]["allowed_tools"].append("terminal")

    response = run_adk_runtime_request(payload)

    assert response["status"] == "error"
    assert response["error"] == "adk_surface_mismatch"
    assert response["field"] == "surface.allowed_tools"
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_adk_adapter.py -q -o 'addopts='
```

Expected: FAIL because `agent_builder.api.adk_adapter` does not exist.

**Step 3: Implement minimal adapter**

Create `agent_builder/api/adk_adapter.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_builder.api.service import AgentBuilderService
from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.control_plane.models import IncomingMessage


def _error(error: str, **extra: Any) -> dict[str, Any]:
    return {"status": "error", "error": error, **extra}


def _validate_adk_surface(payload: dict[str, Any]) -> dict[str, Any] | None:
    surface_payload = payload.get("surface")
    if not isinstance(surface_payload, dict):
        return _error("invalid_request", field="surface", reason="object_required")

    incoming = IncomingMessage(
        tenant_id=payload["tenant_id"],
        workspace_id=payload["workspace_id"],
        agent_instance_id=payload["agent_instance_id"],
        external_user_ref=payload["external_user_ref"],
        channel=payload["channel"],
        thread_id=payload.get("thread_id"),
        message=payload["message"],
    )
    context = DemoIdentityResolver().resolve_turn(incoming)
    expected = DemoCapabilityResolver().resolve(context)

    checks = (
        ("surface.allowed_toolsets", surface_payload.get("allowed_toolsets"), list(expected.allowed_toolsets)),
        ("surface.allowed_tools", surface_payload.get("allowed_tools"), list(expected.allowed_tools)),
        ("surface.policy_snapshot_id", surface_payload.get("policy_snapshot_id"), expected.policy_snapshot_id),
    )
    for field, actual, wanted in checks:
        if actual != wanted:
            return _error("adk_surface_mismatch", field=field, expected=wanted, actual=actual)
    return None


def run_adk_runtime_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _error("invalid_request", field="payload", reason="object_required")
    adk_run_id = payload.get("adk_run_id")
    if not isinstance(adk_run_id, str) or not adk_run_id.strip():
        return _error("invalid_request", field="adk_run_id", reason="required_string")

    surface_error = _validate_adk_surface(payload)
    if surface_error is not None:
        return surface_error

    audit_path = payload.get("audit_path")
    service_payload = {k: v for k, v in payload.items() if k not in {"adk_run_id", "surface", "audit_path"}}
    service = AgentBuilderService(audit_path=Path(audit_path) if audit_path else None)
    response = service.run(service_payload)
    if response.get("status") != "ok":
        return {"adk_run_id": adk_run_id, **response}
    return {
        "adk_run_id": adk_run_id,
        "hermes_run_id": response["run_id"],
        **response,
    }
```

**Step 4: Run focused tests**

```bash
python3 -m pytest tests/agent_builder/test_adk_adapter.py tests/agent_builder/test_agent_builder_service.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add agent_builder/api/adk_adapter.py tests/agent_builder/test_adk_adapter.py
git commit -m "feat: add ADK runtime adapter smoke contract"
```

### Task 11.2: Add stdin/stdout smoke command for ADK calls

**Objective:** Provide a small command that ADK integration tests can invoke without importing Hermes internals.

**Files:**
- Create: `agent_builder/api/adk_run_request.py`
- Test: `tests/agent_builder/test_adk_run_request.py`

**Step 1: Write failing test**

```python
import json
import subprocess
import sys


def test_adk_run_request_accepts_json_stdin(tmp_path):
    payload = {
        "adk_run_id": "adk_run_cli_001",
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(tmp_path / "events.jsonl"),
        "surface": {
            "allowed_toolsets": ["agent_builder_erp_read"],
            "allowed_tools": ["erp_get_customer", "erp_list_orders"],
            "policy_snapshot_id": "policy_demo_readonly_v1",
        },
    }

    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.adk_run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "ok"
    assert response["adk_run_id"] == "adk_run_cli_001"
    assert response["hermes_run_id"].startswith("run_")
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_adk_run_request.py -q -o 'addopts='
```

Expected: FAIL because the module does not exist.

**Step 3: Implement command**

Create `agent_builder/api/adk_run_request.py`:

```python
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
```

**Step 4: Run focused tests**

```bash
python3 -m pytest tests/agent_builder/test_adk_adapter.py tests/agent_builder/test_adk_run_request.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add agent_builder/api/adk_run_request.py tests/agent_builder/test_adk_run_request.py
git commit -m "feat: add ADK runtime smoke command"
```

---

## Phase 12 — Integration and denial matrix

### Task 12.1: Add permitted + denied ADK integration smoke

**Objective:** Prove the permitted ADK request executes and a proposed forbidden tool fails closed without creating unsafe runtime access.

**Files:**
- Create: `tests/agent_builder/test_adk_integration_smoke.py`

**Step 1: Write integration tests**

```python
import json
import subprocess
import sys


def _payload(tmp_path):
    return {
        "adk_run_id": "adk_run_integration_001",
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(tmp_path / "events.jsonl"),
        "surface": {
            "allowed_toolsets": ["agent_builder_erp_read"],
            "allowed_tools": ["erp_get_customer", "erp_list_orders"],
            "policy_snapshot_id": "policy_demo_readonly_v1",
        },
    }


def _run(payload):
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.adk_run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_adk_permitted_request_and_audit_projection(tmp_path):
    response = _run(_payload(tmp_path))

    assert response["status"] == "ok"
    assert response["tool_events"]

    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            response["audit_event_path"],
            "--session-key",
            response["session_key"],
            "--run-id",
            response["hermes_run_id"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    audit_payload = json.loads(audit.stdout)
    assert len(audit_payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in audit_payload["events"])


def test_adk_forbidden_tool_surface_is_denied_before_runtime(tmp_path):
    payload = _payload(tmp_path)
    payload["surface"]["allowed_tools"] = ["erp_get_customer", "erp_list_orders", "terminal"]

    response = _run(payload)

    assert response["status"] == "error"
    assert response["error"] == "adk_surface_mismatch"
```

**Step 2: Run integration smoke**

```bash
python3 -m pytest tests/agent_builder/test_adk_integration_smoke.py -q -o 'addopts='
```

Expected: PASS.

**Step 3: Commit**

```bash
git add tests/agent_builder/test_adk_integration_smoke.py
git commit -m "test: add ADK Hermes integration smoke"
```

## Final verification gate

Run before closing this plan:

```bash
python3 -m pytest tests/agent_builder -q -o 'addopts='
python3 -m compileall -q agent_builder tools/agent_builder_erp_read_tool.py tests/agent_builder
printf '%s' '{"adk_run_id":"adk_run_gate_001","tenant_id":"tenant_demo","workspace_id":"workspace_demo","agent_instance_id":"agent_sales_assistant","external_user_ref":"whatsapp:+551****9999","channel":"whatsapp","thread_id":null,"message":"Quais pedidos o cliente ACME tem em aberto?","mode":"contract","surface":{"allowed_toolsets":["agent_builder_erp_read"],"allowed_tools":["erp_get_customer","erp_list_orders"],"policy_snapshot_id":"policy_demo_readonly_v1"}}' | python3 -m agent_builder.api.adk_run_request
git diff --check
git status --short
```

Expected:

- All Agent Builder tests pass.
- Compileall exits 0.
- ADK smoke returns `status: ok`, `adk_run_id`, `hermes_run_id`, and only `agent_builder_erp_read` tools.
- `git diff --check` exits 0.
- Worktree is clean after final commit.

## Implementation order summary

1. Task 11.1: ADK adapter contract and mismatch denial.
2. Task 11.2: ADK stdin/stdout smoke command.
3. Task 12.1: permitted/denied integration smoke and audit projection.

## Next authorized step

Open/update the PR with the completed hardening work and this plan. Then implement **Task 11.1** only after the PR context is reviewed or the user explicitly asks to execute the next implementation tranche.
