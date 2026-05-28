from langchain_core.tools import tool

from agent_starter.security import permissions as perm


@tool
def pub() -> str:
    """public."""
    return "p"


@tool
def secret() -> str:
    """needs perm."""
    return "s"


def setup_function():
    perm.clear_tool_permissions()


def test_no_declaration_is_public():
    assert perm.filter_tools_for_permissions([pub], granted=set()) == [pub]


def test_required_perm_filtered_when_not_granted():
    perm.register_tool_permissions("secret", ["todo.write"])
    assert perm.filter_tools_for_permissions([pub, secret], granted=set()) == [pub]
    assert {t.name for t in perm.filter_tools_for_permissions([pub, secret], granted={"todo.write"})} == {"pub", "secret"}


def test_granted_none_means_no_restriction():
    perm.register_tool_permissions("secret", ["todo.write"])
    assert len(perm.filter_tools_for_permissions([pub, secret], granted=None)) == 2


def test_granted_permissions_reads_state():
    assert perm.granted_permissions({}) is None                       # 无信息→不限制
    assert perm.granted_permissions({"permissions": ["a"]}) == {"a"}
    assert perm.granted_permissions({"user_scope": {"permissions": ["b"]}}) == {"b"}
