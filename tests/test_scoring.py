"""Performance Score transparency."""
from phantom_tweeks.engine import score


def test_every_subscore_explains_itself():
    ps = score.compute()
    assert ps.subscores
    for s in ps.subscores:
        assert len(s.explanation) > 30, f"{s.name} has no real explanation"


def test_unmeasurable_inputs_are_none_not_fabricated():
    ps = score.compute()
    gaming = next(s for s in ps.subscores if s.name == "Gaming Performance")
    assert gaming.value is None
    assert "does not estimate" in gaming.explanation


def test_scores_are_bounded():
    ps = score.compute()
    for s in ps.subscores:
        if s.value is not None:
            assert 0 <= s.value <= 100
    if ps.overall is not None:
        assert 0 <= ps.overall <= 100


def test_render_lists_all_categories():
    out = score.compute().render()
    for name in ("Gaming Performance", "CPU Health", "GPU Health", "Memory",
                 "Storage", "Network", "Background Load", "System Configuration"):
        assert name in out
