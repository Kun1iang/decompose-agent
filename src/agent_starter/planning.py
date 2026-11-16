"""Structured retrieval-plan parsing and validation.

The decomposition LLM proposes independent retrieval steps.  This module turns
that untrusted JSON into validated ``{question, tool, arguments}`` steps before
the graph is allowed to execute any tools.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class _StepDraft(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class PlanParseResult:
    steps: list[dict[str, Any]]
    used_fallback: bool
    reason: str = ""


def strip_json_fence(raw: str) -> str:
    """Remove a surrounding Markdown code fence from model output."""
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def render_tool_catalog(tools: list[BaseTool]) -> str:
    """Render the read-tool contract included in the decomposition prompt."""
    blocks: list[str] = []
    for tool in tools:
        params = []
        for name, meta in (tool.args or {}).items():
            param_type = meta.get("type", "string")
            default = repr(meta.get("default", ""))
            params.append(f"{name}: {param_type}, 默认 {default}")
        param_text = "；".join(params) if params else "无参数"
        description = (tool.description or "").strip().replace("\n", " ")
        blocks.append(f"- {tool.name}: {description}\n  参数：{param_text}")
    return "\n".join(blocks)


def _normalize_arguments(tool: BaseTool, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise TypeError("arguments must be an object")
    if tool.args_schema is None:
        return {}

    validated = tool.args_schema.model_validate(arguments)
    return validated.model_dump(exclude_none=True)


def _normalize_step(
    raw: Any,
    tool_map: dict[str, BaseTool],
) -> dict[str, Any]:
    draft = _StepDraft.model_validate(raw)
    tool = tool_map.get(draft.tool)
    if tool is None:
        raise ValueError(f"unknown tool: {draft.tool}")
    if not draft.question.strip():
        raise ValueError("question must not be blank")

    arguments = _normalize_arguments(tool, draft.arguments)
    return {
        "question": draft.question.strip(),
        "tool": tool.name,
        "arguments": arguments,
    }


def _dedupe(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for step in steps:
        key = json.dumps(
            [step["tool"], step["arguments"]],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(step)
    return unique


def fallback_plan(
    tools: list[BaseTool],
    user_text: str,
    *,
    max_steps: int,
) -> list[dict[str, Any]]:
    """Safe broad-retrieval fallback used when model planning is unavailable."""
    question = (user_text or "执行全量经营数据检索").strip()
    steps = [
        {"question": question, "tool": tool.name, "arguments": {}}
        for tool in tools[:max_steps]
    ]
    return _dedupe(steps)


def parse_tool_plan(
    raw: str,
    tools: list[BaseTool],
    user_text: str,
    *,
    max_steps: int,
) -> PlanParseResult:
    """Parse a model-proposed plan and fail soft to broad retrieval."""
    tool_map = {tool.name: tool for tool in tools}
    if not tools:
        return PlanParseResult(steps=[], used_fallback=False, reason="no_tools")

    try:
        payload = json.loads(strip_json_fence(raw))
    except (json.JSONDecodeError, TypeError) as exc:
        return PlanParseResult(
            steps=fallback_plan(tools, user_text, max_steps=max_steps),
            used_fallback=True,
            reason=type(exc).__name__,
        )

    raw_steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(raw_steps, list):
        return PlanParseResult(
            steps=fallback_plan(tools, user_text, max_steps=max_steps),
            used_fallback=True,
            reason="invalid_plan_shape",
        )

    valid_steps: list[dict[str, Any]] = []
    for raw_step in raw_steps[:max_steps]:
        try:
            valid_steps.append(_normalize_step(raw_step, tool_map))
        except (TypeError, ValueError) as exc:
            logger.warning(
                "plan.step_rejected",
                error_type=type(exc).__name__,
                index=len(valid_steps),
            )
            continue

    valid_steps = _dedupe(valid_steps)
    if not valid_steps:
        return PlanParseResult(
            steps=fallback_plan(tools, user_text, max_steps=max_steps),
            used_fallback=True,
            reason="no_valid_steps",
        )

    return PlanParseResult(
        steps=valid_steps,
        used_fallback=False,
        reason="partially_invalid" if len(valid_steps) != len(raw_steps) else "",
    )
