#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REGISTRATION_MARKER = "    # scaffold:domains"


class ScaffoldError(RuntimeError):
    pass


def _validate_name(name: str) -> str:
    value = (name or "").strip()
    if not DOMAIN_RE.fullmatch(value):
        raise ScaffoldError("domain name must be lowercase snake_case, for example: ticket or hr_offer")
    return value


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        item = (v or "").strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _domain_files(name: str, label: str, triggers: list[str]) -> dict[str, str]:
    triggers_src = json.dumps(triggers, ensure_ascii=False)
    label_src = json.dumps(label, ensure_ascii=False)
    title = label or name
    success_prefix_src = json.dumps(f"已创建{title}：", ensure_ascii=False)
    prompt = (
        f"你在“{title}”域。用户要创建或查询{title}时，调用对应工具完成；"
        "创建前如果缺标题就先问标题。"
    )
    prompt_src = json.dumps(prompt, ensure_ascii=False)
    return {
        "tools.py": f'''"""Local tools for the {name} domain.

Replace the in-memory store with your DB/API/MCP call when wiring real business logic.
"""
from __future__ import annotations

from langchain_core.tools import tool

_STORE: dict[int, list[dict]] = {{}}
_SEQ = [0]


@tool
async def create_{name}(user_id: int, title: str) -> dict:
    """Create one {name} item. Args: user_id, title."""
    _SEQ[0] += 1
    item = {{"id": _SEQ[0], "title": title, "done": False}}
    _STORE.setdefault(user_id, []).append(item)
    return {{"ok": True, "id": item["id"], "title": title}}


@tool
async def list_{name}_items(user_id: int) -> dict:
    """List {name} items for a user. Args: user_id."""
    return {{"items": list(_STORE.get(user_id, []))}}
''',
        "prompt.py": f'''DOMAIN_PROMPT = {prompt_src}
''',
        "domainspec.py": f'''from agent_starter.tasks.domains import DomainSpec
from agent_starter.tasks.{name}.tools import list_{name}_items

SPEC = DomainSpec(
    name="{name}",
    label={label_src},
    triggers={triggers_src},
    read_tools=[list_{name}_items],
    write_tools=[],
)
''',
        "taskspec.py": f'''from agent_starter.tasks.{name}.prompt import DOMAIN_PROMPT
from agent_starter.tasks.{name}.tools import create_{name}
from agent_starter.tasks.registry import TaskSpec

SPEC = TaskSpec(
    task_type="create_{name}",
    domain="{name}",
    create_tool=create_{name},
    prompt_fragment=DOMAIN_PROMPT,
    success_message=lambda raw: {success_prefix_src} + str(raw.get("title", "")),
)
''',
        "__init__.py": f'''from agent_starter.tasks.domains import register_domain
from agent_starter.tasks.{name}.domainspec import SPEC as DOMAIN_SPEC
from agent_starter.tasks.{name}.taskspec import SPEC as TASK_SPEC
from agent_starter.tasks.registry import REGISTRY


def register() -> None:
    register_domain(DOMAIN_SPEC)
    if TASK_SPEC not in REGISTRY:
        REGISTRY.append(TASK_SPEC)
''',
    }


def _test_file(name: str) -> str:
    return f'''from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r


def setup_function():
    d.clear_registry()
    r.REGISTRY.clear()


def test_{name}_registers_domain_and_task():
    from agent_starter.tasks.{name} import register

    register()

    spec = d.get_domain("{name}")
    assert spec is not None
    assert spec.read_tools
    assert any(task.domain == "{name}" for task in r.REGISTRY)
    assert {{tool.name for tool in d.select_tools_for_state({{"domain": "{name}"}})}} >= {{
        "list_{name}_items",
        "create_{name}",
    }}
'''


def _insert_registration(init_path: Path, name: str) -> None:
    text = init_path.read_text(encoding="utf-8")
    import_line = f"    from agent_starter.tasks import {name}"
    call_line = f"    {name}.register()"
    if import_line in text or call_line in text:
        raise ScaffoldError(f"registration for {name!r} already exists in {init_path}")
    if REGISTRATION_MARKER not in text:
        raise ScaffoldError(f"missing scaffold marker in {init_path}: {REGISTRATION_MARKER.strip()}")
    block = f"{import_line}\n{call_line}\n{REGISTRATION_MARKER}"
    init_path.write_text(text.replace(REGISTRATION_MARKER, block, 1), encoding="utf-8")


def scaffold_domain(
    *,
    repo_root: Path | str,
    name: str,
    label: str | None = None,
    triggers: list[str] | None = None,
) -> list[Path]:
    root = Path(repo_root)
    domain = _validate_name(name)
    display_label = (label or domain.replace("_", " ")).strip()
    trigger_values = _unique([*(triggers or []), display_label, domain])

    tasks_root = root / "src" / "agent_starter" / "tasks"
    domain_dir = tasks_root / domain
    test_dir = root / "tests" / "tasks" / domain
    init_path = tasks_root / "__init__.py"
    if domain_dir.exists():
        raise ScaffoldError(f"domain directory already exists: {domain_dir}")
    if not init_path.is_file():
        raise ScaffoldError(f"missing tasks registry file: {init_path}")

    created: list[Path] = []
    domain_dir.mkdir(parents=True)
    test_dir.mkdir(parents=True)
    for filename, content in _domain_files(domain, display_label, trigger_values).items():
        path = domain_dir / filename
        path.write_text(content, encoding="utf-8")
        created.append(path)
    test_path = test_dir / f"test_{domain}.py"
    test_path.write_text(_test_file(domain), encoding="utf-8")
    created.append(test_path)
    _insert_registration(init_path, domain)
    created.append(init_path)
    return created


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new agent_starter business domain.")
    parser.add_argument("name", help="domain name in lowercase snake_case, e.g. ticket")
    parser.add_argument("--label", default=None, help="human readable label, e.g. 工单")
    parser.add_argument("--trigger", action="append", default=[], help="classification trigger; can be repeated")
    parser.add_argument("--repo-root", default=".", help="repository root, defaults to current directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        created = scaffold_domain(
            repo_root=Path(args.repo_root),
            name=args.name,
            label=args.label,
            triggers=args.trigger,
        )
    except ScaffoldError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("created:")
    for path in created:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
