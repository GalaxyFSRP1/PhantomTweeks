"""Tests for the Tweak Encyclopedia.

The encyclopedia documents tweaks Phantom Tweeks refuses to apply. That makes
it uniquely dangerous if it ever drifts: a HARMFUL entry that gained an
implementation, or a verdict quietly softened, would turn honest documentation
into an endorsement.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import tweakdb  # noqa: E402


def test_catalog_is_substantial_and_unique():
    assert len(tweakdb.TWEAKS) >= 25
    ids = [t.id for t in tweakdb.TWEAKS]
    assert len(ids) == len(set(ids)), "duplicate tweak ids"


def test_every_verdict_is_valid():
    valid = {tweakdb.SAFE, tweakdb.SITUATIONAL, tweakdb.PLACEBO,
             tweakdb.HARMFUL}
    for t in tweakdb.TWEAKS:
        assert t.verdict in valid, f"{t.id} has verdict {t.verdict!r}"


def test_every_tweak_explains_itself():
    """A verdict without reasoning is just an opinion."""
    for t in tweakdb.TWEAKS:
        assert t.summary, f"{t.id} has no summary"
        assert len(t.detail) > 80, f"{t.id} does not justify its verdict"


def test_harmful_tweaks_are_never_implemented():
    """The load-bearing guarantee of this whole module."""
    for t in tweakdb.by_verdict(tweakdb.HARMFUL):
        assert not t.catalog_id, (
            f"{t.id} is marked HARMFUL but claims an implementation "
            f"({t.catalog_id})")
        assert not t.applied_by_us


def test_placebo_tweaks_are_never_implemented():
    """Applying something we call ineffective would be dishonest."""
    for t in tweakdb.by_verdict(tweakdb.PLACEBO):
        assert not t.catalog_id, f"{t.id} is PLACEBO but is implemented"


def test_security_tweaks_are_classified_harmful():
    """Non-negotiable: these must never be softened to 'situational'."""
    must_be_harmful = {
        "disable_defender", "disable_mitigations", "disable_uac",
        "disable_core_isolation", "delete_services", "auto_overclock",
    }
    for tweak_id in must_be_harmful:
        t = tweakdb.BY_ID.get(tweak_id)
        assert t is not None, f"{tweak_id} vanished from the encyclopedia"
        assert t.verdict == tweakdb.HARMFUL, (
            f"{tweak_id} is classified {t.verdict}, must be HARMFUL")


def test_implemented_tweaks_reference_a_real_optimization():
    """A catalog_id pointing at nothing is a broken promise in the UI."""
    catalog_src = (ROOT / "src" / "phantom_tweeks" / "engine"
                   / "catalog.py").read_text(encoding="utf-8")
    real = set(re.findall(r'id="([a-z0-9_.]+)"', catalog_src))
    for t in tweakdb.TWEAKS:
        if t.catalog_id:
            assert t.catalog_id in real, (
                f"{t.id} references catalog id {t.catalog_id!r}, "
                "which does not exist")


def test_search_finds_tweaks_by_registry_value():
    """The main use case: paste a value from a guide, get a verdict."""
    hits = tweakdb.search("SystemResponsiveness")
    assert hits, "cannot look up a registry value users will actually paste"
    assert hits[0].verdict == tweakdb.PLACEBO


def test_search_finds_tweaks_by_alias():
    hits = tweakdb.search("Superfetch")
    assert hits, "aliases are not searchable"


def test_search_orders_dangerous_results_first():
    """If a term matches several tweaks, the warning must not be buried."""
    hits = tweakdb.search("disable")
    verdicts = [h.verdict for h in hits]
    order = {tweakdb.SAFE: 0, tweakdb.SITUATIONAL: 1,
             tweakdb.PLACEBO: 2, tweakdb.HARMFUL: 3}
    assert verdicts == sorted(verdicts, key=lambda v: order[v])


def test_empty_search_returns_nothing():
    assert tweakdb.search("") == []
    assert tweakdb.search("   ") == []


def test_report_covers_every_tweak():
    text = tweakdb.report()
    for t in tweakdb.TWEAKS:
        assert t.name in text, f"{t.id} missing from the report"


def test_no_tweak_promises_a_guaranteed_gain():
    """Even the safe entries must not claim a fixed improvement.

    Hone - the largest product in this space - states plainly that it cannot
    guarantee more FPS. Anything promising a specific number is marketing.
    """
    src = Path(tweakdb.__file__).read_text(encoding="utf-8").lower()
    for phrase in ("guaranteed fps", "guarantees more fps", "+20 fps",
                   "double your fps", "boost fps by", "instant fps"):
        assert phrase not in src, f"encyclopedia promises: {phrase!r}"


def test_the_encyclopedia_is_reachable_from_the_cli():
    cli = (ROOT / "src" / "phantom_tweeks" / "cli"
           / "main.py").read_text(encoding="utf-8")
    assert '"tweaks"' in cli, "no CLI command for the encyclopedia"
    assert "cmd_tweaks" in cli


def test_the_encyclopedia_is_reachable_from_the_gui():
    gui = (ROOT / "src" / "phantom_tweeks" / "gui"
           / "app_window.py").read_text(encoding="utf-8")
    assert '"tweakdb"' in gui, "no GUI page for the encyclopedia"


@pytest.mark.parametrize("verdict", [tweakdb.SAFE, tweakdb.SITUATIONAL,
                                     tweakdb.PLACEBO, tweakdb.HARMFUL])
def test_each_verdict_has_entries(verdict):
    assert tweakdb.by_verdict(verdict), f"no tweaks classified {verdict}"
