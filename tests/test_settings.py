from agent_starter.settings import Settings


def test_settings_boots_without_optional_deps(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    for k in ("AGENT_PG_DSN", "MCP_SERVER_URL", "AGENT_EMBED_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.openai_model == "gpt-4o-mini"
    assert s.agent_pg_dsn == ""       # 可选，默认空
    assert s.mcp_server_url == ""     # 可选，默认空
    assert s.enable_example_domain is False
    assert s.agent_embed_dim == 1536


def test_enable_example_domain_parses_truthy(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("ENABLE_EXAMPLE_DOMAIN", "1")
    assert Settings().enable_example_domain is True
