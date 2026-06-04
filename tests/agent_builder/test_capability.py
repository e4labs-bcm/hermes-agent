from agent_builder.control_plane.capability import DemoCapabilityResolver, PolicyDenied
from agent_builder.control_plane.identity import DemoIdentityResolver
from tests.agent_builder.test_identity import make_message


def make_context(**overrides):
    return DemoIdentityResolver().resolve_turn(make_message(**overrides))


def test_readonly_policy_allows_only_erp_read_toolset_and_tools():
    surface = DemoCapabilityResolver().resolve(make_context())

    assert surface.allowed_toolsets == ("agent_builder_erp_read",)
    assert surface.allowed_tools == ("erp_get_customer", "erp_list_orders")
    assert surface.approval_required_tools == ()


def test_dangerous_hermes_tools_are_explicitly_blocked():
    surface = DemoCapabilityResolver().resolve(make_context())

    for tool in (
        "terminal",
        "browser",
        "file",
        "messaging",
        "cron",
        "cronjob",
        "write_file",
        "send_message",
        "code_execution",
    ):
        assert tool in surface.blocked_tools
        assert not surface.allows_tool(tool)


def test_unknown_tool_fails_closed():
    surface = DemoCapabilityResolver().resolve(make_context())

    assert not surface.allows_tool("erp_delete_order")
    try:
        DemoCapabilityResolver().ensure_tool_allowed(surface, "erp_delete_order")
    except PolicyDenied as exc:
        assert "erp_delete_order" in str(exc)
    else:
        raise AssertionError("unknown tool should fail closed")


def test_capability_surface_is_deterministic_for_same_context():
    resolver = DemoCapabilityResolver()
    context = make_context()

    first = resolver.resolve(context)
    second = resolver.resolve(context)

    assert first == second
    assert first.schema_digest.startswith("sha256:")
