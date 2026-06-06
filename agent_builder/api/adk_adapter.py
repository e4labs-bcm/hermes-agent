"""ADK-shaped adapter for private Agent Builder runtime requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_builder.api.service import AgentBuilderService
from agent_builder.control_plane.capability import DemoCapabilityResolver, PolicyDenied
from agent_builder.control_plane.identity import DemoIdentityResolver, IdentityDenied
from agent_builder.control_plane.models import IncomingMessage

_SERVICE_PAYLOAD_EXCLUDES = {"adk_run_id", "surface", "audit_path"}


def _error(error: str, **extra: Any) -> dict[str, Any]:
    return {"status": "error", "error": error, **extra}


def _incoming_from_payload(payload: dict[str, Any]) -> IncomingMessage:
    return IncomingMessage(
        tenant_id=payload["tenant_id"],
        workspace_id=payload["workspace_id"],
        agent_instance_id=payload["agent_instance_id"],
        external_user_ref=payload["external_user_ref"],
        channel=payload["channel"],
        thread_id=payload.get("thread_id"),
        message=payload["message"],
    )


def _validate_adk_surface(payload: dict[str, Any]) -> dict[str, Any] | None:
    surface_payload = payload.get("surface")
    if not isinstance(surface_payload, dict):
        return _error("invalid_request", field="surface", reason="object_required")

    try:
        incoming = _incoming_from_payload(payload)
        context = DemoIdentityResolver().resolve_turn(incoming)
        expected = DemoCapabilityResolver().resolve(context)
    except KeyError as exc:
        return _error("invalid_request", field=str(exc).strip("'"), reason="required")
    except (TypeError, ValueError) as exc:
        return _error("invalid_request", detail=str(exc))
    except IdentityDenied as exc:
        return _error("identity_denied", detail=str(exc))
    except PolicyDenied as exc:
        return _error("capability_denied", detail=str(exc))

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
    """Validate an ADK-shaped request and run it through the private Hermes boundary."""

    if not isinstance(payload, dict):
        return _error("invalid_request", field="payload", reason="object_required")

    adk_run_id = payload.get("adk_run_id")
    if not isinstance(adk_run_id, str) or not adk_run_id.strip():
        return _error("invalid_request", field="adk_run_id", reason="required_string")

    surface_error = _validate_adk_surface(payload)
    if surface_error is not None:
        return surface_error

    audit_path = payload.get("audit_path")
    service_payload = {k: v for k, v in payload.items() if k not in _SERVICE_PAYLOAD_EXCLUDES}
    service = AgentBuilderService(audit_path=Path(audit_path) if audit_path else None)
    response = service.run(service_payload)
    if response.get("status") != "ok":
        return {"adk_run_id": adk_run_id, **response}
    return {
        "adk_run_id": adk_run_id,
        "hermes_run_id": response["run_id"],
        **response,
    }
