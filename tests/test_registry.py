from langchain_core.tools import tool

from agent_starter.tasks import registry as r


@tool
def _create() -> dict:
    """create tool."""
    return {"ok": True}


def setup_function():
    r.REGISTRY.clear()


def test_register_and_collect_prompt_fragment_by_domain():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="收集 todo 标题再确认创建。",
        success_message=lambda raw: "done",
    ))
    assert r.collect_prompt_fragments_for_domain("todo") == ["收集 todo 标题再确认创建。"]
    assert r.collect_prompt_fragments_for_domain("other") == []


def test_merge_tool_result_into_draft_uses_hook():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "",
        tool_result_to_draft_patches=lambda name, raw: ({"todo_id": raw["id"]} if name == "add_todo" else None),
    ))
    merged = r.merge_tool_result_into_draft("add_todo", {"id": 7}, {"title": "买奶"})
    assert merged == {"title": "买奶", "todo_id": 7}
    # 不认领的 tool 原样返回
    assert r.merge_tool_result_into_draft("other", {}, {"a": 1}) == {"a": 1}


def test_render_success_message_for_create_tool():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: f"done:{raw['id']}",
    ))

    assert r.render_success_message("_create", {"ok": True, "id": 7}) == "done:7"
    assert r.render_success_message("_create", {"ok": False, "id": 7}) is None
    assert r.render_success_message("other", {"ok": True, "id": 7}) is None


def test_should_display_draft_uses_registered_hooks():
    assert r.should_display_draft({"working_draft": {}}) is True
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "",
        is_draft_displayable=lambda state: bool((state.get("working_draft") or {}).get("ready")),
    ))

    assert r.should_display_draft({"working_draft": {"ready": False}}) is False
    assert r.should_display_draft({"working_draft": {"ready": True}}) is True


def test_should_display_draft_only_uses_current_domain_hooks():
    r.REGISTRY.append(r.TaskSpec(
        task_type="todo_create", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "",
        is_draft_displayable=lambda state: True,
    ))
    r.REGISTRY.append(r.TaskSpec(
        task_type="other_create", domain="other", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "",
        is_draft_displayable=lambda state: False,
    ))

    assert r.should_display_draft({"domain": "todo", "working_draft": {}}) is True


def test_registry_hook_errors_do_not_escape():
    r.REGISTRY.append(r.TaskSpec(
        task_type="todo_create", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: (_ for _ in ()).throw(RuntimeError("bad success")),
        render_draft=lambda state: (_ for _ in ()).throw(RuntimeError("bad render")),
        tool_result_to_draft_patches=lambda name, raw: (_ for _ in ()).throw(RuntimeError("bad merge")),
        is_draft_displayable=lambda state: (_ for _ in ()).throw(RuntimeError("bad display")),
    ))

    assert r.render_success_message("_create", {"ok": True}) is None
    assert r.collect_draft_renderings({"domain": "todo", "working_draft": {}}) == []
    assert r.merge_tool_result_into_draft("_create", {"ok": True}, {"a": 1}) == {"a": 1}
    assert r.should_display_draft({"domain": "todo", "working_draft": {}}) is False


def test_success_and_merge_hooks_can_be_scoped_to_domain():
    r.REGISTRY.append(r.TaskSpec(
        task_type="other_create", domain="other", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "other",
        tool_result_to_draft_patches=lambda name, raw: {"domain": "other"},
    ))
    r.REGISTRY.append(r.TaskSpec(
        task_type="todo_create", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "todo",
        tool_result_to_draft_patches=lambda name, raw: {"domain": "todo"},
    ))

    assert r.render_success_message("_create", {"ok": True}, domain="todo") == "todo"
    assert r.merge_tool_result_into_draft("_create", {"ok": True}, {}, domain="todo") == {"domain": "todo"}
