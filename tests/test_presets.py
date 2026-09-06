"""Preset selection must never violate the safety rules."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from phantom_tweeks.engine import presets
from phantom_tweeks.engine.catalog import (CATALOG, Category, Confidence,
                                           Optimization, Risk)


@dataclass
class FakeEval:
    applicable: bool = True
    confidence: Confidence = Confidence.HIGH
    already_optimal: bool = False
    reason: str = ""


@dataclass
class FakeRec:
    optimization: Optimization
    evaluation: FakeEval


def _recs(**over):
    out = []
    for opt in CATALOG:
        out.append(FakeRec(opt, FakeEval(**over)))
    return out


def test_all_presets_have_required_metadata():
    assert presets.PRESETS
    for p in presets.PRESETS:
        assert p.id and p.name and p.tagline and p.description
        assert p.confidences
        assert p.caveat, f"{p.id} makes no honest statement of its limits"


def test_default_preset_exists_and_is_the_strictest():
    p = presets.get(presets.DEFAULT_PRESET)
    assert p is not None
    assert p.confidences == (Confidence.HIGH,)
    assert p.max_risk == Risk.LOW


def test_preset_ids_are_unique():
    ids = [p.id for p in presets.PRESETS]
    assert len(ids) == len(set(ids))


def test_no_preset_ever_selects_a_not_recommended_item():
    """The single most important guarantee."""
    for p in presets.PRESETS:
        assert Confidence.NOT_RECOMMENDED not in p.confidences
        picked = presets.select(p.id, _recs(confidence=Confidence.NOT_RECOMMENDED))
        assert picked == [], f"{p.id} selected a NOT RECOMMENDED optimization"


def test_no_preset_selects_low_confidence_items():
    for p in presets.PRESETS:
        picked = presets.select(p.id, _recs(confidence=Confidence.LOW))
        assert picked == [], f"{p.id} selected a LOW confidence optimization"


def test_no_preset_selects_advanced_items():
    for p in presets.PRESETS:
        for oid in presets.select(p.id, _recs()):
            opt = next(o for o in CATALOG if o.id == oid)
            assert not opt.advanced, f"{p.id} selected advanced item {oid}"


def test_presets_never_select_inapplicable_or_already_optimal():
    for p in presets.PRESETS:
        assert presets.select(p.id, _recs(applicable=False)) == []
        assert presets.select(p.id, _recs(already_optimal=True)) == []


def test_presets_never_select_advisory_only_entries():
    """Entries with no applier cannot be 'applied'; ticking them is a lie."""
    advisory = [o.id for o in CATALOG if o.apply is None]
    assert advisory, "expected at least one advisory-only entry"
    for p in presets.PRESETS:
        picked = set(presets.select(p.id, _recs()))
        assert not (picked & set(advisory)), f"{p.id} ticked an advisory-only item"


def test_preset_respects_its_risk_ceiling():
    for p in presets.PRESETS:
        for oid in presets.select(p.id, _recs(confidence=Confidence.HIGH)):
            opt = next(o for o in CATALOG if o.id == oid)
            assert presets._RISK_ORDER[opt.risk] <= presets._RISK_ORDER[p.max_risk]


def test_safe_is_a_subset_of_balanced():
    safe = set(presets.select("safe", _recs()))
    balanced = set(presets.select("balanced", _recs()))
    assert safe <= balanced


def test_quiet_preset_never_changes_the_power_plan():
    picked = presets.select("quiet", _recs())
    assert "power.high_performance" not in picked


def test_housekeeping_touches_storage_only():
    for oid in presets.select("housekeeping", _recs(confidence=Confidence.HIGH)):
        opt = next(o for o in CATALOG if o.id == oid)
        assert opt.area == "Storage", f"housekeeping selected non-storage {oid}"


def test_competitive_skips_storage():
    for oid in presets.select("competitive", _recs()):
        opt = next(o for o in CATALOG if o.id == oid)
        assert opt.area != "Storage"


def test_unknown_preset_selects_nothing_and_does_not_raise():
    assert presets.select("does-not-exist", _recs()) == []
    assert presets.get("does-not-exist") is None
    assert "Unknown preset" in presets.describe("does-not-exist")


def test_select_tolerates_malformed_recommendations():
    class Junk:
        pass
    assert presets.select("safe", [Junk()]) == []
    assert presets.select("safe", []) == []


def test_describe_mentions_the_caveat():
    for p in presets.PRESETS:
        assert p.caveat in presets.describe(p.id)


def test_preset_areas_reference_real_catalog_areas():
    real = {o.area for o in CATALOG}
    for p in presets.PRESETS:
        for area in p.areas:
            assert area in real, f"{p.id} filters on unknown area {area!r}"


def test_preset_excludes_reference_real_ids():
    real = {o.id for o in CATALOG}
    for p in presets.PRESETS:
        for oid in p.exclude:
            assert oid in real, f"{p.id} excludes unknown id {oid!r}"
