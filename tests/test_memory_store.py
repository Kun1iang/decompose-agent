import pytest

from agent_starter.memory.store import InMemoryStore


@pytest.mark.asyncio
async def test_pref_latest_wins_and_recall():
    s = InMemoryStore()
    await s.upsert_preference(1, "nickname", "老张")
    await s.upsert_preference(1, "nickname", "张哥")  # latest-wins
    r = await s.recall(1, "随便")
    assert [(p.key, p.value) for p in r.prefs] == [("nickname", "张哥")]


@pytest.mark.asyncio
async def test_observations_recent_cap_and_user_isolation():
    s = InMemoryStore()
    for i in range(7):
        await s.add_observation(1, f"o{i}")
    await s.add_observation(2, "other")
    r1 = await s.recall(1, "q")
    assert [o.text for o in r1.observations] == ["o2", "o3", "o4", "o5", "o6"]  # 近 5 条
    r2 = await s.recall(2, "q")
    assert [o.text for o in r2.observations] == ["other"]


@pytest.mark.asyncio
async def test_empty_recall_is_empty():
    r = await InMemoryStore().recall(99, "q")
    assert r.is_empty()
