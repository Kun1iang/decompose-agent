from langchain_core.tools import tool

from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r


@tool
def _r() -> str:
    """read tool."""
    return "r"


@tool
def _w() -> str:
    """write tool."""
    return "w"


def setup_function():
    d.clear_registry()
    r.REGISTRY.clear()


def test_register_and_list():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r], write_tools=[_w], triggers=["待办"]))
    assert [s.name for s in d.list_domains()] == ["todo"]
    assert d.get_domain("todo").label == "待办"


def test_select_tools_global_reads_plus_active_writes():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r], write_tools=[_w]))
    # 命中域：global read ∪ 本域 write
    names = {t.name for t in d.select_tools_for_state({"domain": "todo"})}
    assert names == {"_r", "_w"}
    # 无域：只 global read，不绑 write
    names_no = {t.name for t in d.select_tools_for_state({"domain": ""})}
    assert names_no == {"_r"}


def test_select_tools_extra_appended_and_deduped():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r]))
    names = {t.name for t in d.select_tools_for_state({"domain": "todo"}, extra_tools=[_r, _w])}
    assert names == {"_r", "_w"}  # _r 去重


def test_select_tools_includes_task_create_tool_for_active_domain():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_w,
        prompt_fragment="", success_message=lambda raw: "done",
    ))
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r]))

    names = {t.name for t in d.select_tools_for_state({"domain": "todo"})}
    assert names == {"_r", "_w"}

    names_no = {t.name for t in d.select_tools_for_state({"domain": ""})}
    assert names_no == {"_r"}
