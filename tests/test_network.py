"""Network Lab measurement and honest diagnosis."""
import pytest

from phantom_tweeks.network import lab


def test_diagnosis_stable_when_clean():
    d = lab.diagnose({
        "connection": "Ethernet (eth0)",
        "gateway": {"packet_loss_pct": 0, "jitter_ms": 0.4},
        "internet": {"packet_loss_pct": 0, "jitter_ms": 1.2, "latency_ms": 22},
    })
    assert d["status"] == "STABLE"
    assert d["recommendations"] == ["No change recommended."]


def test_diagnosis_flags_packet_loss():
    d = lab.diagnose({
        "connection": "Wi-Fi (wlan0)",
        "gateway": {"packet_loss_pct": 0, "jitter_ms": 1},
        "internet": {"packet_loss_pct": 2.1, "jitter_ms": 18, "latency_ms": 40},
    })
    assert d["status"] == "UNSTABLE"
    assert "2.1%" in d["summary"]
    assert "18 ms" in d["summary"]


def test_never_promises_dns_fixes_loss():
    d = lab.diagnose({
        "connection": "Ethernet",
        "gateway": {"packet_loss_pct": 0, "jitter_ms": 1},
        "internet": {"packet_loss_pct": 3, "jitter_ms": 20, "latency_ms": 50},
    })
    joined = " ".join(d["recommendations"])
    assert "Changing DNS will not fix" in joined


def test_local_loss_blamed_locally_not_isp():
    d = lab.diagnose({
        "connection": "Wi-Fi (wlan0)",
        "gateway": {"packet_loss_pct": 4, "jitter_ms": 12},
        "internet": {"packet_loss_pct": 4, "jitter_ms": 12, "latency_ms": 40},
    })
    joined = " ".join(d["recommendations"])
    assert "not your ISP" in joined


def test_clean_local_dirty_internet_blames_upstream():
    d = lab.diagnose({
        "connection": "Ethernet",
        "gateway": {"packet_loss_pct": 0, "jitter_ms": 1.0},
        "internet": {"packet_loss_pct": 0, "jitter_ms": 22, "latency_ms": 60},
    })
    joined = " ".join(d["recommendations"])
    assert "ISP or upstream routing" in joined


def test_full_lab_carries_dns_disclaimer():
    notes = " ".join(lab.diagnose({"internet": {}, "gateway": {}}).get("recommendations", []))
    from phantom_tweeks.network.lab import full_lab
    # check the static note text directly to avoid live network in CI
    import inspect
    src = inspect.getsource(full_lab)
    assert "not the same as game-server ping" in src
    assert "does not promise ping reduction" in src


def test_ping_result_handles_no_replies():
    r = lab.ping("192.0.2.1", count=1, timeout_ms=200)   # TEST-NET-1, unroutable
    assert r.packet_loss_pct == 100.0 or r.error
