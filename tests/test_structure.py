from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_tree_does_not_contain_tests():
    hits = [
        p.relative_to(ROOT)
        for p in (ROOT / "src" / "agent_starter").rglob("test_*.py")
    ]
    assert hits == []
