import pytest

from agent_starter.serving.sessions import InMemorySessionStore


@pytest.mark.asyncio
async def test_touch_creates_updates_and_orders():
    s = InMemorySessionStore()
    await s.touch(1, "t1", "第一条消息")
    await s.touch(1, "t2", "另一个会话")
    await s.touch(1, "t1", "新消息")  # 更新 t1 → 排最前；标题保留首条
    lst = await s.list_for_user(1)
    assert [m.thread_id for m in lst] == ["t1", "t2"]
    assert lst[0].title == "第一条消息"


@pytest.mark.asyncio
async def test_delete_and_user_isolation():
    s = InMemorySessionStore()
    await s.touch(1, "t1", "a")
    await s.touch(2, "t2", "b")
    assert await s.delete(1, "t1") is True
    assert await s.delete(1, "nope") is False
    assert [m.thread_id for m in await s.list_for_user(1)] == []
    assert [m.thread_id for m in await s.list_for_user(2)] == ["t2"]
