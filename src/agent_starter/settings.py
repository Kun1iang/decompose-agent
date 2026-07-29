"""精简全局配置。可选项默认空字符串 = 关闭对应能力，保证零依赖启动。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM（必填）----
    llm_provider: str = "deepseek"  # deepseek | openai | custom
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"

    # ---- 基础 ----
    jwt_secret: str = "dev-secret"
    log_level: str = "INFO"
    log_format: str = "console"  # console | json
    agent_workspace_id: int = 1

    # ---- 示例域开关 ----
    enable_example_domain: bool = False

    # ---- skills 目录（Markdown 能力包；目录不存在 = 无 skill）----
    skills_dir: str = "skills"

    # ---- memory：LLM 富偏好抽取（opt-in；默认关 = write 不打 LLM）----
    enable_llm_pref_extraction: bool = False

    # ---- 可选能力（空 = 关闭，后续 plan 接入）----
    agent_pg_dsn: str = ""
    agent_embed_base_url: str = ""
    agent_embed_api_key: str = ""
    agent_embed_model: str = "text-embedding-3-small"
    agent_embed_dim: int = 1536
    mcp_server_url: str = ""
    mcp_request_timeout_seconds: int = 30


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
