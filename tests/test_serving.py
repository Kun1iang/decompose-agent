import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, fake_llm):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("AGENT_PG_DSN", raising=False)  # 走 MemorySaver
    monkeypatch.delenv("ENABLE_EXAMPLE_DOMAIN", raising=False)
    import agent_starter.nodes.agent as agent_mod
    import agent_starter.nodes.classify as classify_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake_llm)
    monkeypatch.setattr(classify_mod, "build_llm", lambda *a, **k: fake_llm)
    from agent_starter.main import app
    with TestClient(app) as c:  # 进入 lifespan：建 graph(MemorySaver) + sessions
        yield c


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_chat_sync_returns_reply(client):
    r = client.post("/agent/chat", json={"message": "在吗", "user_id": 1, "thread_id": "t1"})
    assert r.status_code == 200
    assert r.json()["reply"] == "你好，我是 agent。"


def test_chat_stream_emits_done_with_reply(client):
    r = client.post("/agent/chat/stream", json={"message": "在吗", "user_id": 1, "thread_id": "ts"})
    assert r.status_code == 200
    body = r.text
    assert '"type": "done"' in body
    assert "你好，我是 agent。" in body
    assert '"type": "update"' in body  # 逐节点事件


def test_sessions_listed_after_chat(client):
    client.post("/agent/chat", json={"message": "第一句", "user_id": 7, "thread_id": "tA"})
    data = client.get("/agent/sessions", params={"user_id": 7}).json()
    ids = [s["thread_id"] for s in data["sessions"]]
    assert "tA" in ids
    assert data["sessions"][0]["title"] == "第一句"


def test_session_messages(client):
    client.post("/agent/chat", json={"message": "记住这句", "user_id": 9, "thread_id": "tM"})
    msgs = client.get("/agent/sessions/tM/messages", params={"user_id": 9}).json()["messages"]
    roles = [m["role"] for m in msgs]
    assert "human" in roles and "ai" in roles
    assert any(m["content"] == "记住这句" for m in msgs if m["role"] == "human")


def test_session_messages_are_user_scoped(client):
    client.post("/agent/chat", json={"message": "私有历史", "user_id": 9, "thread_id": "private"})

    r = client.get("/agent/sessions/private/messages", params={"user_id": 10})

    assert r.status_code == 404


def test_session_delete(client):
    client.post("/agent/chat", json={"message": "x", "user_id": 5, "thread_id": "tD"})
    assert client.delete("/agent/sessions/tD", params={"user_id": 5}).json()["deleted"] is True
    ids = [s["thread_id"] for s in client.get("/agent/sessions", params={"user_id": 5}).json()["sessions"]]
    assert "tD" not in ids


def test_chat_request_inputs_carry_security_and_context_fields(client):
    from agent_starter.main import ChatRequest, _inputs

    data = _inputs(ChatRequest(
        message="x",
        user_id=1,
        jwt="token",
        permissions=["todo.read"],
        workspace_id=42,
        page_context={"route": "/todos"},
        user_scope={"permissions": ["todo.write"]},
    ))

    assert data["permissions"] == ["todo.read"]
    assert data["workspace_id"] == 42
    assert data["page_context"] == {"route": "/todos"}
    assert data["user_scope"] == {"permissions": ["todo.write"]}
