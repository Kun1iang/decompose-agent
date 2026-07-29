"""多模型 LLM 构造。支持 DeepSeek、OpenAI 及任何 OpenAI 兼容 API。"""
from langchain_openai import ChatOpenAI

from agent_starter.settings import get_settings

# 已知提供商的默认 base_url
_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    s = get_settings()
    provider = s.llm_provider.lower()

    preset = _PROVIDER_PRESETS.get(provider, {})

    base_url = s.openai_base_url or preset.get("base_url", "https://api.deepseek.com/v1")
    model = s.openai_model or preset.get("model", "deepseek-chat")

    return ChatOpenAI(
        base_url=base_url,
        api_key=s.openai_api_key,
        model=model,
        temperature=temperature,
    )
