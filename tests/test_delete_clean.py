import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "agent_starter"
# core = 整个 src/agent_starter 但排除 tasks/（业务域目录）
BUSINESS_RE = re.compile(r"offer|probation|hr_|opc|solo|talentos", re.IGNORECASE)
EXAMPLE_RE = re.compile(r"example_todo|\btodo\b", re.IGNORECASE)


def _iter_core_py():
    for p in SRC.rglob("*.py"):
        if "tasks" in p.relative_to(SRC).parts:
            continue  # tasks/ 是业务域所在，不算 core
        yield p


def test_core_has_no_legacy_business_names():
    """AC4：core（tasks/ 外）零 talentos 业务名。"""
    hits = [str(p) for p in _iter_core_py() if BUSINESS_RE.search(p.read_text(encoding="utf-8"))]
    assert hits == [], f"core 残留业务名：{hits}"


def test_core_does_not_reference_example_todo():
    """AC3 守卫：core 不 import / 不提 example_todo——删它无需改 core。"""
    hits = [str(p) for p in _iter_core_py() if EXAMPLE_RE.search(p.read_text(encoding="utf-8"))]
    assert hits == [], f"core 引用了示例域（破坏 delete-clean）：{hits}"
