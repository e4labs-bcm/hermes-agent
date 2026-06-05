# Hermes Multitenant

Hermes Multitenant is an MVP branch for running Hermes as a private, governed runtime behind an external product/control plane such as ADK.

## Goal

Provide a safe enterprise-agent runtime path where product identity, tenant/workspace scope, capability resolution, tool access, and audit are resolved before Hermes executes.

The MVP uses a demo Agent Builder path with:

- tenant/workspace/user/agent session resolution
- a read-only `agent_builder_erp_read` capability surface
- a product `ToolGateway` that records `ToolEvent` audit records
- a `contract` runtime mode for offline/local validation
- a gated `live_safe` runtime mode for explicit manual live execution
- JSON stdin/stdout commands that can be called by a future backend adapter

## Architecture boundary

ADK/product control plane owns:

- tenant/workspace/user identity
- agent instance selection
- capability catalog and permissions
- approvals and audit policy
- frontend/API access

Hermes runtime owns:

- executing the already-resolved turn
- seeing only the allowed product toolset
- routing Agent Builder ERP tool calls through `ToolGateway`
- returning runtime metadata and answer payloads

The frontend should not call Hermes directly.

## Implemented MVP path

Primary files:

- `agent_builder/control_plane/identity.py`
- `agent_builder/control_plane/capability.py`
- `agent_builder/tool_gateway/registry.py`
- `agent_builder/tool_gateway/audit.py`
- `agent_builder/runtime/hermes_adapter.py`
- `agent_builder/runtime/tool_context.py`
- `agent_builder/api/service.py`
- `agent_builder/api/run_request.py`
- `agent_builder/api/audit_events.py`
- `agent_builder/api/local_smoke.py`
- `agent_builder/api/live_safe_smoke.py`
- `tools/agent_builder_erp_read_tool.py`
- `toolsets.py`

## Safety constraints

The MVP intentionally does not expose Hermes built-in terminal, file, browser, messaging, cron, or code-execution tools to client agents.

`live_safe` is fail-closed unless:

```bash
AGENT_BUILDER_LIVE_SAFE=1
```

Normal tests mock live runtime behavior and do not call a real model provider.

## Local verification

From the repo root:

```bash
python3 -m pytest tests/agent_builder -q -o 'addopts='
python3 -m compileall -q agent_builder tools/agent_builder_erp_read_tool.py tests/agent_builder
python3 -m agent_builder.api.local_smoke
printf '%s' '{"tenant_id":"tenant_demo","workspace_id":"workspace_demo","agent_instance_id":"agent_sales_assistant","external_user_ref":"whatsapp:+551****9999","channel":"whatsapp","thread_id":null,"message":"Quais pedidos o cliente ACME tem em aberto?","mode":"contract"}' | python3 -m agent_builder.api.run_request
```

Inspect audit events for a session:

```bash
python3 -m agent_builder.api.audit_events \
  --audit-path /path/to/events.jsonl \
  --session-key 'tenant_demo:workspace_demo:agent_sales_assistant:user_001:whatsapp:default'
```

## Current non-goals

- no customer-facing Agent Builder UI
- no write actions
- no approvals/pending actions yet
- no dynamic client editing of tool definitions
- no per-end-user Hermes profiles
- no ungoverned direct Hermes tool access from client agents

## Next milestones

- map ADK capability catalog records into the Hermes `enabled_toolsets` runtime surface
- replace demo ERP mocks with adapter-backed product tools
- add approval flow for write actions
- persist audit events in product storage instead of local JSONL
- containerize/sandbox runtime execution
- add end-to-end ADK-to-Hermes smoke tests
