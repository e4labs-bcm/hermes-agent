"""Fail-closed request validation for Agent Builder backend payloads."""

from __future__ import annotations

import re
from typing import Any

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
EXTERNAL_REF_MAX_LENGTH = 160
MESSAGE_MAX_LENGTH = 4000

REQUIRED_FIELDS = (
    "tenant_id",
    "workspace_id",
    "agent_instance_id",
    "external_user_ref",
    "channel",
    "message",
)
SAFE_ID_FIELDS = ("tenant_id", "workspace_id", "agent_instance_id", "channel")
OPTIONAL_SAFE_ID_FIELDS = ("thread_id",)


class InvalidRequest(ValueError):
    """Raised when an incoming Agent Builder request is not safe to process."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"invalid {field}: {reason}")
        self.field = field
        self.reason = reason


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise InvalidRequest(field, "required_string")
    if not value.strip() or value != value.strip():
        raise InvalidRequest(field, "blank_or_padded")
    return value


def _validate_safe_id(value: str, field: str) -> str:
    if not SAFE_ID_RE.fullmatch(value):
        raise InvalidRequest(field, "unsafe_identifier")
    return value


def validate_request_payload(payload: Any) -> dict[str, Any]:
    """Return a normalized payload or raise InvalidRequest.

    Only opaque identifiers use the strict safe-id charset. external_user_ref is
    a channel-scoped reference and may contain provider-specific punctuation, but
    it is still bounded and newline-free.
    """

    if not isinstance(payload, dict):
        raise InvalidRequest("payload", "object_required")

    normalized = dict(payload)
    for field in REQUIRED_FIELDS:
        if field not in normalized:
            raise InvalidRequest(field, "missing")

    for field in SAFE_ID_FIELDS:
        normalized[field] = _validate_safe_id(_require_string(normalized, field), field)

    thread_id = normalized.get("thread_id")
    if thread_id is not None:
        if not isinstance(thread_id, str):
            raise InvalidRequest("thread_id", "must_be_string_or_null")
        normalized["thread_id"] = _validate_safe_id(_require_string(normalized, "thread_id"), "thread_id")

    external_user_ref = _require_string(normalized, "external_user_ref")
    if len(external_user_ref) > EXTERNAL_REF_MAX_LENGTH or any(ch in external_user_ref for ch in "\r\n"):
        raise InvalidRequest("external_user_ref", "unsafe_external_ref")
    normalized["external_user_ref"] = external_user_ref

    message = _require_string(normalized, "message")
    if len(message) > MESSAGE_MAX_LENGTH:
        raise InvalidRequest("message", "too_long")
    normalized["message"] = message

    mode = normalized.get("mode", "contract")
    if not isinstance(mode, str):
        raise InvalidRequest("mode", "must_be_string")
    normalized["mode"] = mode
    return normalized
