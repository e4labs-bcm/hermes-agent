import json

from agent_builder.control_plane.capability import DemoCapabilityResolver
from agent_builder.control_plane.identity import DemoIdentityResolver
from agent_builder.tool_gateway.audit import JsonlAuditLog
from agent_builder.tool_gateway.registry import ToolGateway
from tests.agent_builder.test_identity import make_message


def make_gateway(tmp_path):
    context = DemoIdentityResolver().resolve_turn(make_message())
    surface = DemoCapabilityResolver().resolve(context)
    audit = JsonlAuditLog(tmp_path / "tool_events.jsonl")
    return ToolGateway(audit), context, surface, audit


def test_erp_get_customer_returns_json_serializable_data_and_audit_event(tmp_path):
    gateway, context, surface, audit = make_gateway(tmp_path)

    result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_get_customer",
        args={"customer_name": "ACME"},
        tool_call_id="call_001",
    )

    assert result["customer"]["id"] == "cust_acme"
    json.dumps(result)
    events = audit.read_events()
    assert len(events) == 1
    assert events[0]["tool_name"] == "erp_get_customer"
    assert events[0]["status"] == "executed"
    assert events[0]["side_effect_committed"] is False


def test_erp_list_orders_returns_open_orders_and_appends_audit(tmp_path):
    gateway, context, surface, audit = make_gateway(tmp_path)

    result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_list_orders",
        args={"customer_id": "cust_acme", "status": "open"},
        tool_call_id="call_002",
    )

    assert result["orders"]
    assert all(order["status"] == "open" for order in result["orders"])
    assert audit.read_events()[0]["status"] == "executed"


def test_unauthorized_tool_is_blocked_and_audited(tmp_path):
    gateway, context, surface, audit = make_gateway(tmp_path)

    result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_delete_order",
        args={"order_id": "ord_001"},
        tool_call_id="call_003",
    )

    assert result["error"] == "tool_not_allowed"
    event = audit.read_events()[0]
    assert event["status"] == "blocked"
    assert event["tool_name"] == "erp_delete_order"
    assert event["side_effect_committed"] is False


def test_invalid_tenant_is_blocked_and_audited(tmp_path):
    gateway, _, surface, audit = make_gateway(tmp_path)
    invalid_context = DemoIdentityResolver().resolve_turn(make_message(tenant_id="tenant_other"))

    result = gateway.call(
        context=invalid_context,
        surface=surface,
        tool_name="erp_get_customer",
        args={"customer_name": "ACME"},
        tool_call_id="call_004",
    )

    assert result["error"] == "tenant_not_authorized"
    event = audit.read_events()[0]
    assert event["status"] == "blocked"
    assert event["tenant_id"] == "tenant_other"


def test_tool_exception_is_failed_and_audited_without_side_effect(tmp_path):
    gateway, context, surface, audit = make_gateway(tmp_path)

    def broken_tool(**_args):
        raise RuntimeError("ERP unavailable")

    gateway._tools["erp_get_customer"] = broken_tool

    result = gateway.call(
        context=context,
        surface=surface,
        tool_name="erp_get_customer",
        args={"customer_name": "ACME"},
        tool_call_id="call_005",
    )

    assert result["error"] == "tool_failed"
    event = audit.read_events()[0]
    assert event["status"] == "failed"
    assert event["side_effect_committed"] is False
