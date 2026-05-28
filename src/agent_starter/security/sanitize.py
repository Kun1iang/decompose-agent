"""用户输入去注入 + 包裹；输出回显清理。轻量、通用——业务可按需加 PII 脱敏。"""
from __future__ import annotations

import re

_INJECTION_RE = re.compile(
    r"(?i)(ignore\s+(?:(?:all|previous|above)\s+)+instructions"
    r"|disregard\s+(all|previous)\s+"
    r"|you\s+are\s+now\s+"
    r"|system\s+prompt"
    r"|忽略(以上|前面|之前|上述).{0,6}(指令|提示|要求|规则)"
    r"|无视(以上|前面|之前).{0,6}(指令|提示))"
)


def sanitize_user_input(text: str) -> str:
    """把明显的越权/注入片段替换成标记，其余原样保留。"""
    return _INJECTION_RE.sub("[已过滤]", text or "")


def wrap_user_input(text: str) -> str:
    """包进定界符——配合 SYSTEM_INSTRUCTIONS，让模型把其中内容当数据而非指令。"""
    return f"<user_input>\n{text}\n</user_input>"


def sanitize_output(text: str) -> str:
    """清掉模型可能回显的定界符。业务可在此叠加 PII 打码等。"""
    t = text or ""
    return t.replace("<user_input>", "").replace("</user_input>", "")
