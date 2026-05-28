import importlib

from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r


def _reset_and_register(enable: bool):
    d.clear_registry()
    r.REGISTRY.clear()
    import agent_starter.tasks as tasks_pkg
    importlib.reload(tasks_pkg)
    tasks_pkg.register_enabled_domains(enable_example=enable)


def test_example_registered_when_enabled():
    _reset_and_register(True)
    assert d.get_domain("todo") is not None
    assert any(s.task_type == "create_todo" for s in r.REGISTRY)


def test_example_absent_when_disabled():
    _reset_and_register(False)
    assert d.get_domain("todo") is None
    assert r.REGISTRY == []
