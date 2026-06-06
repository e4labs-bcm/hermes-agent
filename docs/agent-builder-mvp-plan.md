# Agent Builder MVP Implementation Plan

> Base: clean clone of `https://github.com/NousResearch/hermes-agent.git`.
> Branch: `agent-builder-mvp`.
> Goal: build a small, controlled enterprise-agent MVP on top of Hermes Runtime, without pretending Hermes alone is the SaaS control plane.

## 1. Product direction

We will start from a raw Hermes clone and add the minimum product layer needed to prove the architecture:

1. A backend/control-plane boundary in front of Hermes.
2. Tenant/workspace/user/agent/session resolution before runtime execution.
3. A small capability resolver that decides which tools are visible per turn.
4. A Tool Gateway with read-only mock ERP tools.
5. Append-only ToolEvent audit logs.
6. A Hermes Runtime adapter that calls `AIAgent` with restricted `enabled_toolsets`.
7. A local smoke test proving one user can ask a business question and only read-only tools are available.

No customer-facing Agent Builder UI yet. No write actions. No payments. No destructive tools. No dynamic client editing of tool definitions.

## 2. MVP non-goals

- Do not build full SaaS billing, organizations, SSO, RBAC UI, or admin dashboard yet.
- Do not expose terminal, browser, file, code execution, messaging, cron, or external side-effect tools to client agents.
- Do not rely on prompt text as the security boundary.
- Do not create a Hermes profile per end user.
- Do not allow ERP write actions until persistent approval is implemented.

## 3. Proposed package layout

Create a new product package under:

```text
agent_builder/
  __init__.py
  control_plane/
    __init__.py
    identity.py
    models.py
    capability.py
    sessions.py
  tool_gateway/
    __init__.py
    registry.py
    erp_mock.py
    audit.py
  runtime/
    __init__.py
    hermes_adapter.py
  api/
    __init__.py
    local_smoke.py

tests/agent_builder/
  test_identity.py
  test_capability.py
  test_tool_gateway_audit.py
  test_hermes_adapter_contract.py
```

This keeps the MVP additive. We do not rewrite Hermes internals first. We use Hermes as runtime and only integrate deeper after the boundaries are proven.

## 4. Core runtime contract

### 4.1 Incoming message

```json
{
  "tenant_id": "tenant_demo",
  "workspace_id": "workspace_demo",
  "agent_instance_id": "agent_sales_assistant",
  "external_user_ref": "whatsapp:+5511999999999",
  "channel": "whatsapp",
  "thread_id": null,
  "message": "Quais pedidos o cliente ACME tem em aberto?"
}
```

### 4.2 Resolved turn context

```json
{
  "tenant_id": "tenant_demo",
  "workspace_id": "workspace_demo",
  "agent_instance_id": "agent_sales_assistant",
  "internal_user_id": "user_001",
  "session_key": "tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default",
  "memory_scope": "tenant_demo/workspace_demo/agent_sales_assistant/user_001/session",
  "policy_snapshot_id": "policy_demo_readonly_v1"
}
```

### 4.3 Capability surface

```json
{
  "policy_snapshot_id": "policy_demo_readonly_v1",
  "allowed_toolsets": ["agent_builder_erp_read"],
  "allowed_tools": ["erp_get_customer", "erp_list_orders"],
  "blocked_tools": ["terminal", "browser", "write_file", "send_message", "cronjob"],
  "approval_required_tools": [],
  "schema_digest": "sha256:<computed>"
}
```

### 4.4 ToolEvent

Every Tool Gateway call must append an event:

```json
{
  "event_id": "evt_...",
  "tenant_id": "tenant_demo",
  "workspace_id": "workspace_demo",
  "agent_instance_id": "agent_sales_assistant",
  "internal_user_id": "user_001",
  "session_key": "...",
  "tool_call_id": "...",
  "tool_name": "erp_list_orders",
  "policy_snapshot_id": "policy_demo_readonly_v1",
  "schema_digest": "sha256:<computed>",
  "args_redacted": {},
  "result_redacted": {},
  "status": "executed|blocked|failed",
  "side_effect_committed": false,
  "external_ref": null,
  "duration_ms": 0,
  "created_at": "ISO-8601"
}
```

For this MVP, all ERP tools are read-only, so `side_effect_committed` must always be `false`.

## 5. Implementation phases

### Phase 0 — Clean clone baseline

Status: done.

- Clone path: `/Users/fiuza/Documents/Hermes/agent-builder-mvp/hermes-agent`
- Remote: `https://github.com/NousResearch/hermes-agent.git`
- Branch: `agent-builder-mvp`

### Phase 1 — Add product boundary models

Create dataclasses or Pydantic-free plain dataclasses for:

- `IncomingMessage`
- `ResolvedIdentity`
- `ResolvedTurnContext`
- `CapabilitySurface`
- `ToolEvent`

Keep dependencies minimal. Use stdlib only unless a dependency already exists in Hermes.

Acceptance criteria:

- Tests construct each model.
- Required fields cannot be silently omitted.
- Session key generation includes tenant, workspace, agent instance, internal user, channel, and thread/default.

### Phase 2 — Identity and session resolver

Implement a deterministic resolver for the demo tenant:

- Map `external_user_ref` to `internal_user_id`.
- Create enterprise session key.
- Create memory scope string.
- Return a `ResolvedTurnContext`.

Acceptance criteria:

- Same external user maps to same internal user.
- Different tenants do not produce the same session key.
- Different agent instances do not produce the same session key.

### Phase 3 — Capability resolver

Implement a read-only policy resolver:

- Allow only `agent_builder_erp_read` toolset.
- Allow only `erp_get_customer` and `erp_list_orders`.
- Explicitly block dangerous Hermes tool categories.
- Compute a stable schema/policy digest.

Acceptance criteria:

- Terminal/file/browser/messaging/cron/code execution are not in allowed tools.
- Unknown tools fail closed.
- Capability surface is deterministic for same input.

### Phase 4 — Tool Gateway read-only mock ERP

Implement two mock tools:

- `erp_get_customer(customer_name)`
- `erp_list_orders(customer_id, status="open")`

These tools should not directly expose Hermes built-in tools. They are product tools.

Acceptance criteria:

- Calls return JSON-serializable dicts.
- Invalid tenant or unauthorized tool returns blocked event.
- Every call writes a `ToolEvent` to an append-only JSONL file under a local MVP data directory.

### Phase 5 — Hermes Runtime adapter

Implement adapter that can run in two modes:

1. Contract-only mode for tests: verifies that the correct context and toolsets would be passed to Hermes.
2. Live mode later: creates `AIAgent(..., enabled_toolsets=[...], skip_context_files=True or controlled)`.

For the first iteration, do not require a real LLM call in tests.

Acceptance criteria:

- Adapter refuses to run without a `CapabilitySurface`.
- Adapter only passes allowed toolsets.
- Adapter includes tenant/session metadata in runtime context.
- Unit tests do not call external LLM providers.

### Phase 6 — Local smoke entrypoint

Create `agent_builder/api/local_smoke.py` that runs one local demo request through:

1. Incoming message
2. Identity resolver
3. Capability resolver
4. Mock Tool Gateway call
5. Audit log verification
6. Contract-only Hermes adapter

Acceptance criteria:

- Command exits 0.
- Prints session key.
- Prints allowed toolsets.
- Prints audit event path.
- Does not invoke terminal/browser/file/messaging toolsets.

Suggested command:

```bash
python -m agent_builder.api.local_smoke
```

## 6. First implementation checklist

- [ ] Create `agent_builder/` package.
- [ ] Create `tests/agent_builder/` tests.
- [ ] Implement dataclasses.
- [ ] Implement resolver tests first.
- [ ] Implement identity/session resolver.
- [ ] Implement capability resolver.
- [ ] Implement mock ERP Tool Gateway.
- [ ] Implement JSONL audit append.
- [ ] Implement contract-only Hermes adapter.
- [ ] Implement local smoke script.
- [ ] Run focused tests.
- [ ] Run local smoke command.

## 7. Test commands

Focused tests:

```bash
python -m pytest tests/agent_builder -q -o 'addopts='
```

Smoke:

```bash
python -m agent_builder.api.local_smoke
```

Repo status:

```bash
git status --short
git diff -- docs/agent-builder-mvp-plan.md
```

## 8. Decision

We will build the MVP additively on top of the clean Hermes clone. The first code commit should prove control-plane identity, capability policy, Tool Gateway audit, and Hermes runtime adapter contract before any UI or customer-facing builder is attempted.
