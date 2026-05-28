import pytest
from langchain_core.messages import HumanMessage

from agent_starter.nodes.agent import agent_loop_action
from agent_starter.skills.loader import (
    Skill,
    load_skills,
    render_skills_section,
    select_skills,
    set_skills,
)
from tests.conftest import FakeLLM

_SKILL_MD = """---
name: concise-style
description: 用户希望更简洁
keywords: [简洁, concise]
---

把回答压到最短：先结论，不啰嗦。
"""


def test_load_skill_from_dir(tmp_path):
    d = tmp_path / "skills" / "concise"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    skills = load_skills(tmp_path / "skills")
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "concise-style"
    assert s.description == "用户希望更简洁"
    assert s.keywords == ["简洁", "concise"]
    assert "先结论" in s.body


def test_load_missing_dir_returns_empty(tmp_path):
    assert load_skills(tmp_path / "nope") == []


def test_select_by_keyword():
    s = Skill(name="concise-style", description="简洁", body="b", keywords=["简洁"])
    assert select_skills("回答简洁点", [s]) == [s]
    assert select_skills("查个天气", [s]) == []


def test_render_section_contains_body():
    s = Skill(name="x", description="d", body="要简洁", keywords=["简洁"])
    out = render_skills_section([s])
    assert "可用技能" in out and "要简洁" in out
    assert render_skills_section([]) == ""


@pytest.mark.asyncio
async def test_relevant_skill_injected_into_agent_system():
    set_skills([Skill(name="concise-style", description="简洁", body="要简洁：先结论", keywords=["简洁"])])
    llm = FakeLLM(reply="好的")
    await agent_loop_action(
        {"messages": [HumanMessage(content="回答简洁点")], "domain": "", "user_id": 1}, llm=llm,
    )
    system = llm.calls[0][0][1]
    assert "要简洁：先结论" in system


@pytest.mark.asyncio
async def test_irrelevant_skill_not_injected():
    set_skills([Skill(name="concise-style", description="简洁", body="要简洁：先结论", keywords=["简洁"])])
    llm = FakeLLM(reply="好的")
    await agent_loop_action(
        {"messages": [HumanMessage(content="查个天气")], "domain": "", "user_id": 1}, llm=llm,
    )
    assert "要简洁：先结论" not in llm.calls[0][0][1]
