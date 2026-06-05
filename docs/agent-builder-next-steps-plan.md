# Agent Builder Next Steps Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the current Agent Builder MVP contract into a locally callable backend path, register the read-only ERP toolset as a real Hermes-visible toolset, run a live-safe Hermes adapter smoke, and expose audit/session inspection.

**Architecture:** Keep ADK/product control plane concepts outside Hermes core while adding only the minimum Hermes integration required for a governed read-only toolset. The Agent Builder path resolves identity and capability before runtime execution, exposes only product tools through a Tool Gateway, and derives audit/session claims from `ToolEvent` records instead of assistant text.

**Tech Stack:** Python stdlib first, existing Hermes tool registry (`tools/registry.py`), `toolsets.py`, existing `AIAgent` runtime, pytest with `-o 'addopts='`. Do not introduce FastAPI or another web framework unless the repo already has one enabled for the API server; start with a stdlib handler/service and CLI smoke.

---

## Current state

Implemented and verified in commit `85b8d3095`:

- `agent_builder/control_plane/models.py` defines `IncomingMessage`, `ResolvedIdentity`, `ResolvedTurnContext`, `CapabilitySurface`, and `ToolEvent`.
- `agent_builder/control_plane/identity.py` resolves demo external users to internal users and creates enterprise session context.
- `agent_builder/control_plane/capability.py` returns the read-only `agent_builder_erp_read` surface, blocks dangerous Hermes tool categories, and computes a deterministic digest.
- `agent_builder/tool_gateway/registry.py` exposes only `erp_get_customer` and `erp_list_orders` through the product Tool Gateway and writes JSONL `ToolEvent`s for executed, blocked, and failed calls.
- `agent_builder/runtime/hermes_adapter.py` supports contract mode and prepares live-mode `AIAgent` kwargs with restricted `enabled_toolsets`.
- `agent_builder/api/local_smoke.py` proves the local contract path from incoming message to audit event and adapter contract.
- `tests/agent_builder/` currently has 24 passing tests.

Verification commands from current baseline:

```bash
python3 -m pytest tests/agent_builder -q -o 'addopts='
python3 -m agent_builder.api.local_smoke
git status --short
```

## Primary gaps

1. The smoke path is a CLI function, not a backend-callable service boundary.
2. `agent_builder_erp_read` exists as a capability contract, but is not yet registered as a real Hermes toolset/tool schema.
3. Live mode is intentionally unexercised; there is no safe live smoke proving `AIAgent` sees only the read-only product tools.
4. Audit is written, but there is no inspection/query interface for sessions or events.

## Desired contract

### Request shape

```json
{
  "tenant_id": "tenant_demo",
  "workspace_id": "workspace_demo",
  "agent_instance_id": "agent_sales_assistant",
  "external_user_ref": "whatsapp:+551****9999",
  "channel": "whatsapp",
  "thread_id": null,
  "message": "Quais pedidos o cliente ACME tem em aberto?",
  "mode": "contract"
}
```

### Run response shape

```json
{
  "status": "ok",
  "mode": "contract|live_safe",
  "session_key": "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default",
  "policy_snapshot_id": "policy_demo_readonly_v1",
  "schema_digest": "sha256:...",
  "allowed_toolsets": ["agent_builder_erp_read"],
  "allowed_tools": ["erp_get_customer", "erp_list_orders"],
  "tool_events": ["evt_..."],
  "audit_event_path": "/.../agent_builder_mvp_tool_events.jsonl",
  "answer": "..."
}
```

### Audit/session response shape

```json
{
  "session_key": "...",
  "events": [
    {
      "event_id": "evt_...",
      "tool_name": "erp_list_orders",
      "status": "executed",
      "side_effect_committed": false,
      "duration_ms": 0,
      "created_at": "ISO-8601"
    }
  ]
}
```

## Non-goals for this plan

- No customer-facing Agent Builder UI.
- No write actions.
- No approvals/pending actions yet.
- No billing, SSO, RBAC UI, admin dashboard, or dynamic client editing of tool definitions.
- No exposure of terminal, browser, file, code execution, messaging, cron, or external side-effect tools to client agents.
- No Hermes profile per end user.
- No live LLM calls in the normal unit test suite.

## Safety constraints for live-safe work

- `mode="live_safe"` must be rejected unless `AGENT_BUILDER_LIVE_SAFE=1` is present in the process environment. This applies to `AgentBuilderService`, `run_request.py`, and `live_safe_smoke.py`, not only to the smoke command.
- Hermes tool wrappers must call the Agent Builder `ToolGateway` so actual runtime tool calls create `ToolEvent` audit records. They must not bypass the gateway by calling `erp_mock` directly.
- Hermes tool wrappers must fail closed when no Agent Builder runtime context is active. A direct call without context should return a JSON error and/or raise a controlled policy error, and should never expose built-in Hermes tools.
- Unit tests must mock `AIAgent` and never make live provider calls. Manual live runs require explicit user approval plus `AGENT_BUILDER_LIVE_SAFE=1`.

## Authority boundaries

| Component | Owns | Does not own |
| --- | --- | --- |
| `IncomingMessage` | Raw product/channel request contract | Auth, policy, or tool execution |
| `DemoIdentityResolver` | Tenant/workspace/user/session/memory-scope resolution | Capability decisions or model prompts |
| `DemoCapabilityResolver` | Per-turn toolset/tool allowlist and blocked categories | Tool execution or audit persistence |
| `ToolGateway` | Product tool dispatch and ToolEvent creation | Hermes built-in tool access |
| `JsonlAuditLog` | Append/read local ToolEvent JSONL | Authorization decisions |
| Hermes tool module | Tool schemas/handlers visible to `AIAgent` | Tenant/session resolution |
| `HermesRuntimeAdapter` | Runtime invocation contract and safe mode selection | Product policy computation |
| API service boundary | Request/response orchestration | Direct frontend access to Hermes internals |

---

## Phase 7 — Local API/service wrapper

### Task 7.1: Extract a reusable Agent Builder service

**Objective:** Move the CLI smoke orchestration into a reusable service function that can be called by CLI, tests, and a future HTTP adapter.

**Files:**
- Create: `agent_builder/api/service.py`
- Modify: `agent_builder/api/local_smoke.py`
- Test: `tests/agent_builder/test_agent_builder_service.py`

**Step 1: Write failing test**

Create `tests/agent_builder/test_agent_builder_service.py`:

```python
from agent_builder.api.service import AgentBuilderService


def test_service_run_contract_returns_backend_response_shape(tmp_path):
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")

    response = service.run(
        {
            "tenant_id": "tenant_demo",
            "workspace_id": "workspace_demo",
            "agent_instance_id": "agent_sales_assistant",
            "external_user_ref": "whatsapp:+551****9999",
            "channel": "whatsapp",
            "thread_id": None,
            "message": "Quais pedidos o cliente ACME tem em aberto?",
            "mode": "contract",
        }
    )

    assert response["status"] == "ok"
    assert response["mode"] == "contract"
    assert response["session_key"] == "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default"
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]
    assert response["allowed_tools"] == ["erp_get_customer", "erp_list_orders"]
    assert response["tool_events"]
    assert response["audit_event_path"].endswith("events.jsonl")
    assert "terminal" not in response["allowed_toolsets"]


def test_service_rejects_live_safe_without_env_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_BUILDER_LIVE_SAFE", raising=False)
    service = AgentBuilderService(audit_path=tmp_path / "events.jsonl")

    response = service.run(
        {
            "tenant_id": "tenant_demo",
            "workspace_id": "workspace_demo",
            "agent_instance_id": "agent_sales_assistant",
            "external_user_ref": "whatsapp:+551****9999",
            "channel": "whatsapp",
            "thread_id": None,
            "message": "Quais pedidos o cliente ACME tem em aberto?",
            "mode": "live_safe",
        }
    )

    assert response["status"] == "error"
    assert response["error"] == "live_safe_requires_explicit_env_gate"
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_agent_builder_service.py -q -o 'addopts='
```

Expected: FAIL because `agent_builder.api.service` does not exist.

**Step 3: Implement minimal service**

This first service is still a demo orchestration boundary: in contract mode it performs the deterministic ACME read-only ERP calls before the adapter. Actual live-safe model tool calls are handled in Phase 8 through gateway-backed Hermes tool wrappers, so they are also audited.

Create `agent_builder/api/service.py`:

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.control_plane.models import IncomingMessage
from agent_builder.runtime.hermes_adapter import HermesRuntimeAdapter
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway


class AgentBuilderService:
    def __init__(self, audit_path: str | Path | None = None) -> None:
        if audit_path is None:
            audit_path = Path(tempfile.gettempdir()) / "agent_builder_mvp_tool_events.jsonl"
        self.audit = JsonlAuditLog(audit_path)
        self.identity_resolver = DemoIdentityResolver()
        self.capability_resolver = DemoCapabilityResolver()
        self.gateway = ToolGateway(self.audit)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("mode", "contract")
        if mode not in {"contract", "live_safe"}:
            return {"status": "error", "error": "unsupported_mode"}
        if mode == "live_safe" and os.getenv("AGENT_BUILDER_LIVE_SAFE") != "1":
            return {
                "status": "error",
                "error": "live_safe_requires_explicit_env_gate",
                "detail": "Set AGENT_BUILDER_LIVE_SAFE=1 only after explicit user approval.",
            }

        incoming = IncomingMessage(
            tenant_id=payload["tenant_id"],
            workspace_id=payload["workspace_id"],
            agent_instance_id=payload["agent_instance_id"],
            external_user_ref=payload["external_user_ref"],
            channel=payload["channel"],
            thread_id=payload.get("thread_id"),
            message=payload["message"],
        )
        context = self.identity_resolver.resolve_turn(incoming)
        surface = self.capability_resolver.resolve(context)

        customer_result = self.gateway.call(
            context=context,
            surface=surface,
            tool_name="erp_get_customer",
            args={"customer_name": "ACME"},
            tool_call_id="service_customer_001",
        )
        orders_result = self.gateway.call(
            context=context,
            surface=surface,
            tool_name="erp_list_orders",
            args={"customer_id": customer_result["customer"]["id"], "status": "open"},
            tool_call_id="service_orders_001",
        )

        if mode == "contract":
            adapter_result = HermesRuntimeAdapter(mode="contract").run_contract(
                context=context,
                surface=surface,
                message=incoming.message,
            )
            answer = f"Contrato validado; {len(orders_result['orders'])} pedidos em aberto."
        else:
            adapter_result = HermesRuntimeAdapter(mode="live_safe").run_live_safe(
                context=context,
                surface=surface,
                gateway=self.gateway,
                message=incoming.message,
            )
            answer = adapter_result["response"]

        events = self.audit.read_events()
        session_events = [e for e in events if e["session_key"] == context.session_key]
        return {
            "status": "ok",
            "mode": mode,
            "session_key": context.session_key,
            "policy_snapshot_id": surface.policy_snapshot_id,
            "schema_digest": surface.schema_digest,
            "allowed_toolsets": list(surface.allowed_toolsets),
            "allowed_tools": list(surface.allowed_tools),
            "tool_events": [e["event_id"] for e in session_events],
            "audit_event_path": str(self.audit.path),
            "answer": answer,
            "runtime_metadata": adapter_result["runtime_metadata"],
        }
```

**Step 4: Update smoke CLI to call service**

Modify `agent_builder/api/local_smoke.py` so `run_smoke()` delegates to `AgentBuilderService.run()` and preserves the existing output fields expected by `tests/agent_builder/test_local_smoke.py`.

**Step 5: Run focused tests**

```bash
python3 -m pytest tests/agent_builder/test_agent_builder_service.py tests/agent_builder/test_local_smoke.py -q -o 'addopts='
```

Expected: PASS.

**Step 6: Commit**

```bash
git add agent_builder/api/service.py agent_builder/api/local_smoke.py tests/agent_builder/test_agent_builder_service.py
git commit -m "feat: add agent builder service boundary"
```

### Task 7.2: Add a stdlib CLI/API handler for JSON requests

**Objective:** Provide a backend-callable command that accepts JSON on stdin and returns JSON on stdout, avoiding a premature web framework dependency.

**Files:**
- Create: `agent_builder/api/run_request.py`
- Test: `tests/agent_builder/test_run_request.py`

**Step 1: Write failing test**

```python
import json
import subprocess
import sys


def test_run_request_accepts_json_stdin_and_returns_json(tmp_path):
    payload = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(tmp_path / "events.jsonl"),
    }

    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "ok"
    assert response["mode"] == "contract"
    assert response["allowed_toolsets"] == ["agent_builder_erp_read"]


def test_run_request_rejects_live_safe_without_env_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_BUILDER_LIVE_SAFE", raising=False)
    payload = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "live_safe",
        "audit_path": str(tmp_path / "events.jsonl"),
    }

    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["status"] == "error"
    assert response["error"] == "live_safe_requires_explicit_env_gate"
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_run_request.py -q -o 'addopts='
```

Expected: FAIL because `run_request.py` does not exist.

**Step 3: Implement minimal command**

`agent_builder/api/run_request.py` reads stdin JSON, pops optional `audit_path`, calls `AgentBuilderService`, and prints sorted JSON.

**Step 4: Run tests**

```bash
python3 -m pytest tests/agent_builder/test_agent_builder_service.py tests/agent_builder/test_run_request.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Manual smoke**

```bash
printf '%s' '{"tenant_id":"tenant_demo","workspace_id":"workspace_demo","agent_instance_id":"agent_sales_assistant","external_user_ref":"whatsapp:+551****9999","channel":"whatsapp","thread_id":null,"message":"Quais pedidos o cliente ACME tem em aberto?","mode":"contract"}' | python3 -m agent_builder.api.run_request
```

Expected: JSON with `status: ok`, `allowed_toolsets: ["agent_builder_erp_read"]`, and at least two `tool_events`.

**Step 6: Commit**

```bash
git add agent_builder/api/run_request.py tests/agent_builder/test_run_request.py
git commit -m "feat: add agent builder json request runner"
```

---

## Phase 8 — Register `agent_builder_erp_read` as a Hermes toolset

### Task 8.1: Add gateway-backed Hermes tool wrappers for Agent Builder ERP read tools

**Objective:** Register `erp_get_customer` and `erp_list_orders` in Hermes' central tool registry under the `agent_builder_erp_read` toolset, while ensuring runtime calls go through the Agent Builder `ToolGateway` and produce `ToolEvent` audit records.

**Files:**
- Create: `agent_builder/runtime/tool_context.py`
- Create: `tools/agent_builder_erp_read_tool.py`
- Test: `tests/agent_builder/test_hermes_tool_registration.py`

**Step 1: Write failing tests**

```python
import json

import tools.agent_builder_erp_read_tool  # noqa: F401 - forces registry side effect
from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.runtime.tool_context import agent_builder_tool_context
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway
from tests.agent_builder.test_identity import make_message
from tools.registry import registry


def make_runtime_tool_context(tmp_path):
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    audit = JsonlAuditLog(tmp_path / "events.jsonl")
    return {
        "context": context,
        "surface": surface,
        "gateway": ToolGateway(audit),
        "audit": audit,
    }


def test_agent_builder_erp_tools_are_registered():
    entry = registry.get_entry("erp_get_customer")
    assert entry is not None
    assert entry.toolset == "agent_builder_erp_read"

    names = registry.get_tool_names_for_toolset("agent_builder_erp_read")
    assert names == ["erp_get_customer", "erp_list_orders"]


def test_erp_get_customer_handler_uses_gateway_and_audits(tmp_path):
    runtime_context = make_runtime_tool_context(tmp_path)
    token = agent_builder_tool_context.set(runtime_context)
    try:
        entry = registry.get_entry("erp_get_customer")
        payload = json.loads(entry.handler({"customer_name": "ACME"}))
    finally:
        agent_builder_tool_context.reset(token)

    assert payload["customer"]["id"] == "cust_acme"
    events = runtime_context["audit"].read_events()
    assert len(events) == 1
    assert events[0]["tool_name"] == "erp_get_customer"
    assert events[0]["side_effect_committed"] is False


def test_erp_tool_handler_fails_closed_without_runtime_context():
    entry = registry.get_entry("erp_get_customer")
    payload = json.loads(entry.handler({"customer_name": "ACME"}))

    assert payload["error"] == "agent_builder_runtime_context_required"
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_hermes_tool_registration.py -q -o 'addopts='
```

Expected: FAIL because `agent_builder.runtime.tool_context` and the Hermes tool module do not exist.

**Step 3: Implement runtime tool context**

Create `agent_builder/runtime/tool_context.py`:

```python
from __future__ import annotations

from contextvars import ContextVar
from typing import Any


agent_builder_tool_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "agent_builder_tool_context",
    default=None,
)
```

**Step 4: Implement gateway-backed wrappers**

Create `tools/agent_builder_erp_read_tool.py`:

```python
import json
import uuid

from agent_builder.runtime.tool_context import agent_builder_tool_context
from tools.registry import registry


def _available() -> bool:
    return True


def _call_gateway(tool_name: str, args: dict) -> str:
    runtime_context = agent_builder_tool_context.get()
    if runtime_context is None:
        return json.dumps({"error": "agent_builder_runtime_context_required"})

    result = runtime_context["gateway"].call(
        context=runtime_context["context"],
        surface=runtime_context["surface"],
        tool_name=tool_name,
        args=args,
        tool_call_id=f"hermes_{uuid.uuid4().hex}",
    )
    return json.dumps(result, ensure_ascii=False)


def _get_customer_handler(args, **_kwargs):
    return _call_gateway("erp_get_customer", {"customer_name": args["customer_name"]})


def _list_orders_handler(args, **_kwargs):
    return _call_gateway(
        "erp_list_orders",
        {"customer_id": args["customer_id"], "status": args.get("status", "open")},
    )


registry.register(
    name="erp_get_customer",
    toolset="agent_builder_erp_read",
    schema={
        "name": "erp_get_customer",
        "description": "Read-only lookup of a customer through the Agent Builder Tool Gateway.",
        "parameters": {
            "type": "object",
            "properties": {"customer_name": {"type": "string"}},
            "required": ["customer_name"],
        },
    },
    handler=_get_customer_handler,
    check_fn=_available,
    requires_env=[],
    description="Gateway-audited read-only Agent Builder ERP customer lookup",
    emoji="🏢",
)

registry.register(
    name="erp_list_orders",
    toolset="agent_builder_erp_read",
    schema={
        "name": "erp_list_orders",
        "description": "Read-only order listing through the Agent Builder Tool Gateway.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "status": {"type": "string", "default": "open"},
            },
            "required": ["customer_id"],
        },
    },
    handler=_list_orders_handler,
    check_fn=_available,
    requires_env=[],
    description="Gateway-audited read-only Agent Builder ERP order listing",
    emoji="📦",
)
```

**Step 5: Run focused tests**

```bash
python3 -m pytest tests/agent_builder/test_hermes_tool_registration.py -q -o 'addopts='
```

Expected: PASS.

**Step 6: Commit**

```bash
git add agent_builder/runtime/tool_context.py tools/agent_builder_erp_read_tool.py tests/agent_builder/test_hermes_tool_registration.py
git commit -m "feat: register gateway-backed agent builder erp tools"
```

### Task 8.2: Add `agent_builder_erp_read` to `toolsets.py`

**Objective:** Make `agent_builder_erp_read` resolvable by `enabled_toolsets=[...]`.

**Files:**
- Modify: `toolsets.py`
- Test: `tests/agent_builder/test_hermes_tool_registration.py`

**Step 1: Add failing test**

```python
from toolsets import resolve_toolset


def test_agent_builder_erp_read_toolset_resolves_only_erp_tools():
    assert resolve_toolset("agent_builder_erp_read") == ["erp_get_customer", "erp_list_orders"]
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_hermes_tool_registration.py -q -o 'addopts='
```

Expected: FAIL because `toolsets.py` does not know the toolset yet.

**Step 3: Modify `toolsets.py`**

Add near other basic toolsets:

```python
"agent_builder_erp_read": {
    "description": "Read-only Agent Builder demo ERP tools for controlled enterprise-agent runs",
    "tools": ["erp_get_customer", "erp_list_orders"],
    "includes": [],
},
```

Do not add these tools to `_HERMES_CORE_TOOLS`.

**Step 4: Run focused and regression tests**

```bash
python3 -m pytest tests/agent_builder/test_hermes_tool_registration.py tests/agent_builder/test_capability.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add toolsets.py tests/agent_builder/test_hermes_tool_registration.py
git commit -m "feat: add agent builder erp read toolset"
```

### Task 8.3: Ensure runtime adapter sees registered tools only

**Objective:** Verify the adapter's allowed toolsets map to exactly the registered read-only tools.

**Files:**
- Modify: `tests/agent_builder/test_hermes_adapter_contract.py`
- Optional modify: `agent_builder/runtime/hermes_adapter.py`

**Step 1: Add failing/guard test**

```python
from toolsets import resolve_toolset


def test_adapter_allowed_toolsets_resolve_to_readonly_erp_tools_only():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="contract")

    kwargs = adapter.build_live_agent_kwargs(context=context, surface=surface)
    resolved = []
    for toolset in kwargs["enabled_toolsets"]:
        resolved.extend(resolve_toolset(toolset))

    assert sorted(resolved) == ["erp_get_customer", "erp_list_orders"]
    assert "terminal" not in resolved
    assert "send_message" not in resolved
```

**Step 2: Run test**

```bash
python3 -m pytest tests/agent_builder/test_hermes_adapter_contract.py -q -o 'addopts='
```

Expected: PASS after Task 8.2. If it fails, fix only the adapter/toolset mapping.

**Step 3: Commit**

```bash
git add tests/agent_builder/test_hermes_adapter_contract.py agent_builder/runtime/hermes_adapter.py
git commit -m "test: guard agent builder runtime toolset surface"
```

---

## Phase 9 — Live-safe adapter test

### Task 9.1: Add explicit `live_safe` mode without requiring live tests

**Objective:** Make live execution opt-in and visibly safer than generic `live`, while keeping unit tests offline.

**Files:**
- Modify: `agent_builder/runtime/hermes_adapter.py`
- Modify: `tests/agent_builder/test_hermes_adapter_contract.py`

**Step 1: Write failing tests**

```python

def test_live_safe_kwargs_keep_context_and_memory_controlled():
    context, surface = make_context_and_surface()
    adapter = HermesRuntimeAdapter(mode="live_safe")

    kwargs = adapter.build_live_agent_kwargs(context=context, surface=surface)

    assert kwargs["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert kwargs["skip_context_files"] is True
    assert kwargs["skip_memory"] is True
    assert kwargs["platform"] == "agent_builder"
    assert kwargs["session_id"] == context.session_key


def test_plain_live_mode_is_not_supported_for_agent_builder():
    with pytest.raises(ValueError, match="live_safe"):
        HermesRuntimeAdapter(mode="live")
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_hermes_adapter_contract.py -q -o 'addopts='
```

Expected: FAIL because adapter currently accepts `live`, not `live_safe`.

**Step 3: Implement minimal adapter change**

- Change `RuntimeMode` to `Literal["contract", "live_safe"]`.
- Reject `live` with a message that tells developers to use `live_safe`.
- Rename `run_live()` to `run_live_safe()`.
- Change `run_live_safe()` to require a `gateway: ToolGateway` argument; do not create a new gateway inside the adapter because the service-owned audit path is the source of truth.
- Keep lazy `from run_agent import AIAgent` inside `run_live_safe()`.
- Keep `skip_context_files=True`, `skip_memory=True`, and restricted `enabled_toolsets`.
- Set `agent_builder_tool_context` around `agent.chat(message)` with `{"context": context, "surface": surface, "gateway": gateway}` so Hermes ERP tool handlers call the scoped `ToolGateway` and audit actual runtime tool calls. Reset the contextvar in a `finally` block.

**Step 4: Run tests**

```bash
python3 -m pytest tests/agent_builder/test_hermes_adapter_contract.py tests/agent_builder/test_agent_builder_service.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add agent_builder/runtime/hermes_adapter.py tests/agent_builder/test_hermes_adapter_contract.py tests/agent_builder/test_agent_builder_service.py
git commit -m "feat: add live-safe agent builder runtime mode"
```

### Task 9.2: Add mock-AIAgent live-safe test

**Objective:** Prove live-safe invocation passes only allowed toolsets without calling a real provider.

**Files:**
- Modify: `tests/agent_builder/test_hermes_adapter_contract.py`

**Step 1: Add failing test with monkeypatch**

```python
import types
import sys


def test_run_live_safe_instantiates_aiagent_with_readonly_toolset(tmp_path, monkeypatch):
    context, surface = make_context_and_surface()
    captured = {}

    class FakeAIAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def chat(self, message):
            return "ACME tem 2 pedidos em aberto."

    fake_run_agent = types.SimpleNamespace(AIAgent=FakeAIAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    from agent_builder.tool_gateway.audit import JsonlAuditLog
    from agent_builder.tool_gateway.registry import ToolGateway

    gateway = ToolGateway(JsonlAuditLog(tmp_path / "events.jsonl"))
    result = HermesRuntimeAdapter(mode="live_safe").run_live_safe(
        context=context,
        surface=surface,
        gateway=gateway,
        message="Quais pedidos o cliente ACME tem em aberto?",
    )

    assert captured["enabled_toolsets"] == ["agent_builder_erp_read"]
    assert result["mode"] == "live_safe"
    assert "2 pedidos" in result["response"]


def test_run_live_safe_resets_agent_builder_tool_context(tmp_path, monkeypatch):
    from agent_builder.runtime.tool_context import agent_builder_tool_context
    from agent_builder.tool_gateway.audit import JsonlAuditLog
    from agent_builder.tool_gateway.registry import ToolGateway

    context, surface = make_context_and_surface()

    class FakeAIAgent:
        def __init__(self, **_kwargs):
            pass

        def chat(self, _message):
            assert agent_builder_tool_context.get() is not None
            return "ok"

    fake_run_agent = types.SimpleNamespace(AIAgent=FakeAIAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    gateway = ToolGateway(JsonlAuditLog(tmp_path / "events.jsonl"))

    HermesRuntimeAdapter(mode="live_safe").run_live_safe(
        context=context,
        surface=surface,
        gateway=gateway,
        message="Oi",
    )

    assert agent_builder_tool_context.get() is None
```

**Step 2: Run focused test**

```bash
python3 -m pytest tests/agent_builder/test_hermes_adapter_contract.py -q -o 'addopts='
```

Expected: PASS after Task 9.1.

**Step 3: Commit**

```bash
git add tests/agent_builder/test_hermes_adapter_contract.py
git commit -m "test: verify live-safe hermes adapter invocation"
```

### Task 9.3: Add manual live-safe smoke command gated by env var

**Objective:** Add a command that can call a real LLM only when explicitly enabled, while staying skipped by default in tests.

**Files:**
- Create: `agent_builder/api/live_safe_smoke.py`
- Create: `tests/agent_builder/test_live_safe_smoke.py`

**Step 1: Write test for default safety gate**

```python
import subprocess
import sys


def test_live_safe_smoke_requires_explicit_env_gate():
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.live_safe_smoke"],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert "AGENT_BUILDER_LIVE_SAFE=1" in completed.stderr
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_live_safe_smoke.py -q -o 'addopts='
```

Expected: FAIL because command does not exist.

**Step 3: Implement command**

`agent_builder/api/live_safe_smoke.py` should:

- Exit 2 unless `AGENT_BUILDER_LIVE_SAFE=1`.
- Build the same demo request as local smoke with `mode="live_safe"`.
- Call `AgentBuilderService.run()` after the env gate; the service must also enforce the same gate, so this command is not the only protection.
- Print response JSON.
- Never set or expand toolsets beyond `agent_builder_erp_read`.

**Step 4: Run default safety test**

```bash
python3 -m pytest tests/agent_builder/test_live_safe_smoke.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Optional manual live run**

Only run when the user explicitly approves a real model call:

```bash
AGENT_BUILDER_LIVE_SAFE=1 python3 -m agent_builder.api.live_safe_smoke
```

Expected: response JSON with `mode: live_safe`, `allowed_toolsets: ["agent_builder_erp_read"]`, and no terminal/browser/file/messaging/cron tool access.

**Step 6: Commit**

```bash
git add agent_builder/api/live_safe_smoke.py tests/agent_builder/test_live_safe_smoke.py
git commit -m "feat: add gated live-safe smoke command"
```

---

## Phase 10 — Audit/session inspection API

### Task 10.1: Add audit query helpers

**Objective:** Query audit events by session key without exposing raw unrestricted logs.

**Files:**
- Modify: `agent_builder/tool_gateway/audit.py`
- Test: `tests/agent_builder/test_audit_query.py`

**Step 1: Write failing test**

```python
from agent_builder.api.service import AgentBuilderService
from agent_builder.tool_gateway.audit import JsonlAuditLog


def test_audit_log_lists_events_for_session(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    response = AgentBuilderService(audit_path=audit_path).run({
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
    })

    events = JsonlAuditLog(audit_path).events_for_session(response["session_key"])

    assert len(events) == 2
    assert {event["tool_name"] for event in events} == {"erp_get_customer", "erp_list_orders"}
    assert all(event["side_effect_committed"] is False for event in events)
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_audit_query.py -q -o 'addopts='
```

Expected: FAIL because `events_for_session()` does not exist.

**Step 3: Implement helper**

Add to `JsonlAuditLog`:

```python
def events_for_session(self, session_key: str) -> list[dict[str, Any]]:
    return [event for event in self.read_events() if event.get("session_key") == session_key]
```

**Step 4: Run tests**

```bash
python3 -m pytest tests/agent_builder/test_audit_query.py tests/agent_builder/test_tool_gateway_audit.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add agent_builder/tool_gateway/audit.py tests/agent_builder/test_audit_query.py
git commit -m "feat: query agent builder audit events by session"
```

### Task 10.2: Add audit inspection command

**Objective:** Provide a backend-callable session audit inspection command.

**Files:**
- Create: `agent_builder/api/audit_events.py`
- Test: `tests/agent_builder/test_audit_events_command.py`

**Step 1: Write failing test**

```python
import json
import subprocess
import sys

from agent_builder.api.service import AgentBuilderService


def test_audit_events_command_returns_session_events(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    run_response = AgentBuilderService(audit_path=audit_path).run({
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
    })

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            str(audit_path),
            "--session-key",
            run_response["session_key"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["session_key"] == run_response["session_key"]
    assert len(payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in payload["events"])
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/agent_builder/test_audit_events_command.py -q -o 'addopts='
```

Expected: FAIL because command does not exist.

**Step 3: Implement command**

`agent_builder/api/audit_events.py` should use `argparse`, read `--audit-path` and `--session-key`, call `JsonlAuditLog.events_for_session()`, and print:

```json
{"session_key":"...","events":[...]}
```

**Step 4: Run tests**

```bash
python3 -m pytest tests/agent_builder/test_audit_events_command.py tests/agent_builder/test_audit_query.py -q -o 'addopts='
```

Expected: PASS.

**Step 5: Commit**

```bash
git add agent_builder/api/audit_events.py tests/agent_builder/test_audit_events_command.py
git commit -m "feat: add agent builder audit events command"
```

### Task 10.3: Add final integration smoke for phases 7-10

**Objective:** Verify service run, Hermes toolset registration, live-safe gate, and audit inspection in one local test path.

**Files:**
- Create: `tests/agent_builder/test_next_steps_integration.py`

**Step 1: Write integration test**

```python
import json
import subprocess
import sys

from toolsets import resolve_toolset


def test_next_steps_contract_integration(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    request = {
        "tenant_id": "tenant_demo",
        "workspace_id": "workspace_demo",
        "agent_instance_id": "agent_sales_assistant",
        "external_user_ref": "whatsapp:+551****9999",
        "channel": "whatsapp",
        "thread_id": None,
        "message": "Quais pedidos o cliente ACME tem em aberto?",
        "mode": "contract",
        "audit_path": str(audit_path),
    }

    run = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.run_request"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    response = json.loads(run.stdout)

    assert response["status"] == "ok"
    assert resolve_toolset("agent_builder_erp_read") == ["erp_get_customer", "erp_list_orders"]

    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_builder.api.audit_events",
            "--audit-path",
            str(audit_path),
            "--session-key",
            response["session_key"],
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    audit_payload = json.loads(audit.stdout)

    assert len(audit_payload["events"]) == 2
    assert all(event["side_effect_committed"] is False for event in audit_payload["events"])
```

**Step 2: Run integration test**

```bash
python3 -m pytest tests/agent_builder/test_next_steps_integration.py -q -o 'addopts='
```

Expected: PASS.

**Step 3: Run full Agent Builder test suite**

```bash
python3 -m pytest tests/agent_builder -q -o 'addopts='
python3 -m agent_builder.api.local_smoke
```

Expected: all tests pass and smoke exits 0.

**Step 4: Commit**

```bash
git add tests/agent_builder/test_next_steps_integration.py
git commit -m "test: add agent builder next steps integration smoke"
```

---

## Final verification gate

Run these before declaring Phases 7-10 complete:

```bash
python3 -m pytest tests/agent_builder -q -o 'addopts='
python3 -m compileall -q agent_builder tools/agent_builder_erp_read_tool.py tests/agent_builder
python3 -m agent_builder.api.local_smoke
printf '%s' '{"tenant_id":"tenant_demo","workspace_id":"workspace_demo","agent_instance_id":"agent_sales_assistant","external_user_ref":"whatsapp:+551****9999","channel":"whatsapp","thread_id":null,"message":"Quais pedidos o cliente ACME tem em aberto?","mode":"contract"}' | python3 -m agent_builder.api.run_request
git diff --check
git status --short
```

Expected:

- All Agent Builder tests pass.
- Compileall exits 0.
- Local smoke returns `allowed_toolsets: ["agent_builder_erp_read"]` and `forbidden_toolsets_absent: true`.
- JSON request runner returns `status: ok`.
- `git diff --check` exits 0.
- `git status --short` is clean after final commit.

## Implementation order summary

1. Phase 7: service boundary + JSON request runner.
2. Phase 8: Hermes registry wrappers + `toolsets.py` mapping.
3. Phase 9: explicit `live_safe` mode + gated manual smoke.
4. Phase 10: audit query helpers + audit inspection command + integration smoke.

## Next authorized step

Phases 7-10 have been implemented and locally verified. Continue with `docs/adk-hermes-integration-smoke-plan.md`, starting from PR review/merge context and then **Task 11.1: Add ADK payload validator**. Do not start live-safe real provider calls until the user explicitly authorizes `AGENT_BUILDER_LIVE_SAFE=1`.
