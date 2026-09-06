"""Tests for the bufferbloat measurement.

The critical property here is that it must NEVER report a grade it did not
measure. During development every ping timed out (ICMP was blocked) and the
first implementation substituted the timeout value for each phase - so all
three phases matched, the difference was zero, and it confidently reported
grade A+ on a connection it had never successfully pinged once.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.network import bufferbloat as bb  # noqa: E402


def _phases(idle, down, up):
    r = bb.BufferbloatResult()
    r.idle = bb.Phase("Idle", idle, (idle or 0) + 2, 20)
    r.download = bb.Phase("While downloading", down, (down or 0) + 5, 20)
    r.upload = bb.Phase("While uploading", up, (up or 0) + 5, 20)
    return r


def test_never_grades_what_it_did_not_measure():
    """The bug that mattered: no replies must not become grade A+."""
    r = _phases(None, None, None)
    assert r.measured is False
    assert r.grade == "not measured"
    verdict = " ".join(r.verdict()).lower()
    assert "could not measure" in verdict
    assert "will not guess" in verdict


def test_blocked_icmp_is_explained_not_blamed():
    r = _phases(None, None, None)
    r.idle.error = "no replies - ICMP is probably blocked"
    text = " ".join(r.verdict()).lower()
    assert "icmp" in text
    assert "does not mean your connection is bad" in text


def test_a_totally_failed_burst_reports_nothing(monkeypatch):
    """A burst where every ping times out must return no median at all."""
    class Dead:
        latency_ms = None

    monkeypatch.setattr(bb.lab, "ping", lambda *a, **k: Dead())
    phase = bb._ping_burst(0.4)
    assert phase.median_ms is None, (
        "a phase with zero replies produced a number anyway")
    assert phase.error


def test_partial_loss_counts_against_you(monkeypatch):
    """Loss under load IS the symptom - it must not be silently dropped."""
    seq = []

    class Reply:
        def __init__(self, ms):
            self.latency_ms = ms

    def fake_ping(*a, **k):
        seq.append(1)
        return Reply(20.0) if len(seq) % 2 else Reply(None)

    monkeypatch.setattr(bb.lab, "ping", fake_ping)
    phase = bb._ping_burst(0.6)
    assert phase.median_ms is not None
    assert phase.lost > 0, "lost packets were not recorded"
    assert phase.worst_ms >= 1000, "a timeout was not counted as bad"


@pytest.mark.parametrize("added,expected", [
    (2, "A+"), (20, "A"), (45, "B"), (150, "C"), (300, "D"), (900, "F"),
])
def test_grade_boundaries(added, expected):
    assert bb.grade_for(added) == expected


def test_grade_is_unknown_without_data():
    assert bb.grade_for(None) == "?"


def test_good_connection_is_reported_as_good():
    r = _phases(18, 20, 21)
    assert r.grade == "A+"
    assert "holds up well" in r.verdict()[0]


def test_severe_bloat_gives_actionable_advice():
    r = _phases(25, 400, 450)
    advice = " ".join(r.verdict())
    assert r.grade in ("D", "F")
    assert "SQM" in advice, "does not name the actual fix"
    assert "router" in advice.lower()
    # It must be honest that PC-side tweaks cannot fix this.
    assert "no registry tweak" in advice.lower()


def test_asymmetric_upload_is_called_out():
    r = _phases(20, 40, 300)
    assert "upload is noticeably worse" in " ".join(r.verdict())


def test_measured_requires_idle_and_one_load_phase():
    assert _phases(20, 40, None).measured is True
    assert _phases(20, None, 40).measured is True
    assert _phases(20, None, None).measured is False
    assert _phases(None, 40, 40).measured is False


def test_report_explains_why_idle_ping_is_misleading():
    text = _phases(20, 25, 26).render().lower()
    assert "idle ping" in text
    assert "busy" in text


def test_module_does_not_claim_to_lower_ping():
    src = Path(bb.__file__).read_text(encoding="utf-8").lower()
    for claim in ("lowers your ping", "reduce your ping", "better ping",
                  "faster ping"):
        assert claim not in src, f"bufferbloat promises: {claim!r}"
