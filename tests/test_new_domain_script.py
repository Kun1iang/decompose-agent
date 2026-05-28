from __future__ import annotations

import importlib.util
import py_compile
from pathlib import Path

import pytest


def _load_new_domain_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "new_domain.py"
    spec = importlib.util.spec_from_file_location("new_domain", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_minimal_repo(root: Path) -> None:
    tasks = root / "src" / "agent_starter" / "tasks"
    tests = root / "tests" / "tasks"
    tasks.mkdir(parents=True)
    tests.mkdir(parents=True)
    (tasks / "__init__.py").write_text(
        "\n".join([
            "def register_enabled_domains(enable_example: bool | None = None) -> None:",
            "    # scaffold:domains",
            "    return None",
            "",
        ]),
        encoding="utf-8",
    )


def test_scaffold_domain_creates_domain_files_and_registration(tmp_path):
    mod = _load_new_domain_module()
    _write_minimal_repo(tmp_path)

    created = mod.scaffold_domain(
        repo_root=tmp_path,
        name="ticket",
        label="工单",
        triggers=["工单", "ticket"],
    )

    domain_dir = tmp_path / "src" / "agent_starter" / "tasks" / "ticket"
    assert {p.name for p in domain_dir.iterdir()} == {
        "__init__.py",
        "domainspec.py",
        "prompt.py",
        "taskspec.py",
        "tools.py",
    }
    assert (tmp_path / "tests" / "tasks" / "ticket" / "test_ticket.py").is_file()
    assert "from agent_starter.tasks import ticket" in (
        tmp_path / "src" / "agent_starter" / "tasks" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "ticket.register()" in (
        tmp_path / "src" / "agent_starter" / "tasks" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "create_ticket" in (domain_dir / "tools.py").read_text(encoding="utf-8")
    assert "DomainSpec" in (domain_dir / "domainspec.py").read_text(encoding="utf-8")
    assert "TaskSpec" in (domain_dir / "taskspec.py").read_text(encoding="utf-8")
    assert domain_dir / "tools.py" in created
    for path in created:
        if path.suffix == ".py":
            py_compile.compile(path, doraise=True)


def test_scaffold_domain_is_idempotency_safe(tmp_path):
    mod = _load_new_domain_module()
    _write_minimal_repo(tmp_path)

    mod.scaffold_domain(repo_root=tmp_path, name="ticket", label="工单", triggers=["工单"])

    with pytest.raises(mod.ScaffoldError, match="already exists"):
        mod.scaffold_domain(repo_root=tmp_path, name="ticket", label="工单", triggers=["工单"])


def test_scaffold_domain_rejects_invalid_domain_name(tmp_path):
    mod = _load_new_domain_module()
    _write_minimal_repo(tmp_path)

    with pytest.raises(mod.ScaffoldError, match="lowercase snake_case"):
        mod.scaffold_domain(repo_root=tmp_path, name="Ticket-App", label="工单", triggers=["工单"])
