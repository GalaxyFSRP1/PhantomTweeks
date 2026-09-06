"""Tests for real driver update checking."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom_tweeks.engine import driverupdate as du  # noqa: E402


def test_never_downloads_or_installs():
    """Driver installers load kernel code. Automating that is how machines
    end up with no display, and automated updaters are a malware vector."""
    src = Path(du.__file__).read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "*", '"""', "'")):
            continue
        for banned in ("urlretrieve", "os.startfile", "Popen", "os.system",
                       "ShellExecute", ".exe\""):
            assert banned not in stripped, (
                f"line {i} may download or run an installer: {stripped[:60]}")


def test_report_states_it_will_not_install():
    text = " ".join(du.report().lower().split())
    assert "never downloads or installs a driver" in text
    assert "malware vector" in text


@pytest.mark.parametrize("windows_version,expected", [
    ("31.0.15.6603", "566.03"),
    ("32.0.15.7602", "576.02"),
    ("30.0.14.9709", "497.09"),
])
def test_windows_driver_version_maps_to_nvidia_version(windows_version,
                                                       expected):
    """Windows reports 31.0.15.6603; NVIDIA calls the same driver 566.03.

    Comparing the raw strings would report every driver as outdated.
    """
    assert du._short_nvidia_version(windows_version) == expected


def test_version_comparison_is_numeric():
    assert du._version_tuple("566.36") > du._version_tuple("566.03")
    assert du._version_tuple("572.16") > du._version_tuple("566.99")
    # Lexicographic comparison would get this wrong.
    assert du._version_tuple("100.0") > du._version_tuple("99.9")


def _fake_nvidia(monkeypatch, latest):
    payload = {"IDS": [{"downloadInfo": {"Version": latest}}]}
    monkeypatch.setattr(du, "_get", lambda url, timeout=15: json.dumps(payload))


def test_detects_an_outdated_driver(monkeypatch):
    _fake_nvidia(monkeypatch, "572.16")
    st = du.check_nvidia("31.0.15.6603", "RTX 4070")
    assert st.checked
    assert st.up_to_date is False
    assert st.download_url


def test_recognises_a_current_driver(monkeypatch):
    _fake_nvidia(monkeypatch, "566.03")
    st = du.check_nvidia("31.0.15.6603", "RTX 4070")
    assert st.up_to_date is True


def test_network_failure_is_reported_not_guessed(monkeypatch):
    def boom(url, timeout=15):
        raise OSError("no route to host")
    monkeypatch.setattr(du, "_get", boom)
    st = du.check_nvidia("31.0.15.6603")
    assert st.checked is False
    assert st.up_to_date is None, "guessed a status without reaching the vendor"
    assert "could not reach" in st.message.lower()


def test_amd_admits_it_cannot_compare():
    """AMD publishes no open version API. Inventing a comparison would be
    worse than saying so."""
    st = du.check_amd("31.0.21912.14", "RX 7800 XT")
    assert st.checked is False
    assert st.up_to_date is None
    assert "does not publish" in st.message
    assert st.download_url


def test_intel_admits_it_cannot_compare():
    st = du.check_intel("31.0.101.5333", "Arc A770")
    assert st.checked is False
    assert "does not publish" in st.message


def test_no_gpu_is_handled(monkeypatch):
    from phantom_tweeks.hardware import monitor
    monkeypatch.setattr(monitor.MONITOR, "gpus", lambda: [])
    results = du.check_all()
    assert len(results) == 1
    assert results[0].checked is False
    assert "no gpu" in results[0].message.lower()


def test_outdated_only_lists_confirmed_results(monkeypatch):
    """An unchecked driver must never appear as outdated."""
    monkeypatch.setattr(du, "check_all", lambda: [
        du.DriverStatus(vendor="AMD", checked=False),
        du.DriverStatus(vendor="NVIDIA", checked=True, up_to_date=True),
        du.DriverStatus(vendor="NVIDIA", checked=True, up_to_date=False),
    ])
    behind = du.outdated()
    assert len(behind) == 1
    assert behind[0].up_to_date is False


def test_report_mentions_ddu_as_the_way_back():
    assert "DDU" in du.report()
