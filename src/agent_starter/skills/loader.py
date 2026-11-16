"""skill 加载/选择/渲染。

skill = 顶层 skills/<name>/SKILL.md（或 skills/<name>.md）：frontmatter（name/description/
keywords）+ 指令正文。运行时按 keywords 命中用户消息选 top-k，正文注入 agent system prompt。
无 skills/ 目录 → 空（零依赖默认）。LLM 语义选 skill 是扩展点（默认走关键词，确定可测）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TOP_K = 3


@dataclass
class Skill:
    name: str
    description: str
    body: str
    keywords: list[str] = field(default_factory=list)


def _parse_list(value: str) -> list[str]:
    v = (value or "").strip().strip("[]")
    return [x.strip().strip("'\"") for x in v.split(",") if x.strip()]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    t = text.lstrip("﻿").strip()
    if not t.startswith("---"):
        return {}, t
    parts = t.split("---", 2)
    if len(parts) < 3:
        return {}, t
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip().lower()] = v.strip()
    return meta, parts[2].strip()


def parse_skill(text: str, fallback_name: str) -> Skill | None:
    meta, body = _parse_frontmatter(text)
    if not body:
        return None
    return Skill(
        name=meta.get("name") or fallback_name,
        description=meta.get("description", ""),
        body=body,
        keywords=_parse_list(meta.get("keywords", "")),
    )


def load_skills(skills_dir: str | Path) -> list[Skill]:
    d = Path(skills_dir)
    if not d.is_dir():
        return []
    out: list[Skill] = []
    seen: set[str] = set()
    paths = sorted(d.glob("*/SKILL.md")) + sorted(d.glob("*.md"))
    for p in paths:
        fallback = p.parent.name if p.name == "SKILL.md" else p.stem
        try:
            skill = parse_skill(p.read_text(encoding="utf-8"), fallback)
        except Exception as e:  # noqa: BLE001  坏文件不拖垮加载
            logger.warning("skill.load_failed", path=str(p), error=str(e))
            continue
        if skill and skill.name not in seen:
            seen.add(skill.name)
            out.append(skill)
    return out


_skills: list[Skill] | None = None


def get_skills() -> list[Skill]:
    global _skills
    if _skills is None:
        try:
            from agent_starter.settings import get_settings
            skills_dir = get_settings().skills_dir
        except Exception:  # noqa: BLE001 - fall back to the repository default
            skills_dir = "skills"
        _skills = load_skills(skills_dir)
    return _skills


def set_skills(skills: list[Skill]) -> None:
    global _skills
    _skills = list(skills)


def reset_skills() -> None:
    global _skills
    _skills = None


def select_skills(query: str, skills: list[Skill], top_k: int = _DEFAULT_TOP_K) -> list[Skill]:
    """按 keywords 命中 query 选相关 skill；命中 0 时回退 name 是否出现在 query。"""
    q = (query or "").lower()
    scored: list[tuple[int, Skill]] = []
    for s in skills:
        score = sum(1 for kw in s.keywords if kw.lower() in q)
        if score == 0 and s.name and s.name.lower() in q:
            score = 1
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_k]]


def render_skills_section(selected: list[Skill]) -> str:
    if not selected:
        return ""
    parts = ["【可用技能（按相关性选中，请遵循）】"]
    for s in selected:
        parts.append(f"## {s.name}\n{s.body.strip()}")
    return "\n\n".join(parts)
