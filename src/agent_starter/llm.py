"""从 settings 构造 ChatOpenAI。"""
from langchain_openai import ChatOpenAI

from agent_starter.settings import get_settings


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        base_url=s.openai_base_url,
        api_key=s.openai_api_key,
        model=s.openai_model,
        temperature=temperature,
    )
