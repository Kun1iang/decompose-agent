import pytest

from agent_starter.tasks.example_todo import tools as t


def setup_function():
    t._STORE.clear()
    t._SEQ[0] = 0


@pytest.mark.asyncio
async def test_add_and_list_and_complete():
    add = await t.add_todo.ainvoke({"user_id": 1, "title": "买牛奶"})
    assert add["ok"] and add["title"] == "买牛奶"
    tid = add["id"]
    listed = await t.list_todos.ainvoke({"user_id": 1})
    assert listed["items"][0]["title"] == "买牛奶"
    assert listed["items"][0]["done"] is False
    done = await t.complete_todo.ainvoke({"user_id": 1, "todo_id": tid})
    assert done["ok"] is True
    listed2 = await t.list_todos.ainvoke({"user_id": 1})
    assert listed2["items"][0]["done"] is True


@pytest.mark.asyncio
async def test_user_isolation():
    await t.add_todo.ainvoke({"user_id": 1, "title": "A"})
    listed_other = await t.list_todos.ainvoke({"user_id": 2})
    assert listed_other["items"] == []
