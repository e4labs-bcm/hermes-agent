from agent_builder.api.service import AgentBuilderService
from agent_builder.tool_gateway.audit import JsonlAuditLog


def test_audit_log_lists_events_for_session(tmp_path):
    audit_path = tmp_path / "events.jsonl"
    response = AgentBuilderService(audit_path=audit_path).run(
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

    events = JsonlAuditLog(audit_path).events_for_session(response["session_key"])

    assert len(events) == 2
    assert {event["tool_name"] for event in events} == {"erp_get_customer", "erp_list_orders"}
    assert all(event["side_effect_committed"] is False for event in events)
