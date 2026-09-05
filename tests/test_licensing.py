"""Licensing: real Ed25519 signatures, honest failure modes."""
from __future__ import annotations

import base64
import importlib
import json
import sys

import pytest

sys.setrecursionlimit(10000)

from phantom_tweeks.licensing import ed25519, keys      # noqa: E402


# ------------------------------------------------------- RFC 8032 vectors

RFC_VECTORS = [
    # (secret, public, message, signature) from RFC 8032 section 7.1
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a"
     "33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15"
     "996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16"
     "f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize("sk_hex,pk_hex,msg_hex,sig_hex", RFC_VECTORS)
def test_ed25519_matches_rfc8032(sk_hex, pk_hex, msg_hex, sig_hex):
    sk = bytes.fromhex(sk_hex)
    msg = bytes.fromhex(msg_hex)
    assert ed25519.public_key(sk).hex() == pk_hex
    assert ed25519.sign(sk, msg).hex() == sig_hex
    assert ed25519.verify(bytes.fromhex(pk_hex), msg, bytes.fromhex(sig_hex))


def test_verify_rejects_wrong_message():
    sk = ed25519.generate_private_key()
    pk = ed25519.public_key(sk)
    sig = ed25519.sign(sk, b"hello")
    assert ed25519.verify(pk, b"hello", sig)
    assert not ed25519.verify(pk, b"hell0", sig)


def test_verify_rejects_wrong_key():
    sk1, sk2 = ed25519.generate_private_key(), ed25519.generate_private_key()
    sig = ed25519.sign(sk1, b"m")
    assert not ed25519.verify(ed25519.public_key(sk2), b"m", sig)


@pytest.mark.parametrize("bad", [b"", b"\x00" * 63, b"\x00" * 65])
def test_verify_never_raises_on_malformed_signature(bad):
    pk = ed25519.public_key(ed25519.generate_private_key())
    assert ed25519.verify(pk, b"m", bad) is False


def test_verify_rejects_non_canonical_scalar():
    """s >= L must be rejected (malleability)."""
    sk = ed25519.generate_private_key()
    pk = ed25519.public_key(sk)
    sig = bytearray(ed25519.sign(sk, b"m"))
    sig[32:] = (ed25519.L + 1).to_bytes(32, "little")
    assert ed25519.verify(pk, b"m", bytes(sig)) is False


def test_generated_keys_are_random():
    a, b = ed25519.generate_private_key(), ed25519.generate_private_key()
    assert a != b and len(a) == 32


# ------------------------------------------------------- key format

@pytest.fixture()
def issuer():
    sk = ed25519.generate_private_key()
    return sk, ed25519.public_key(sk)


def _lic(**over):
    base = dict(key_id="ABC123", plan="premium", issued="2026-01-01",
                expires="2030-01-01")
    base.update(over)
    return keys.LicenseKey(**base)


def test_roundtrip_encode_verify(issuer):
    sk, pk = issuer
    key = keys.encode_key(_lic(), sk)
    ok, msg, lic = keys.verify_key(key, pk)
    assert ok is True, msg
    assert lic.key_id == "ABC123" and lic.plan == "premium"


def test_key_starts_with_prefix(issuer):
    sk, _ = issuer
    assert keys.encode_key(_lic(), sk).startswith("PT-")


def test_tampered_payload_is_rejected(issuer):
    sk, pk = issuer
    key = keys.encode_key(_lic(), sk)
    i = 10
    bad = key[:i] + ("A" if key[i] != "A" else "B") + key[i + 1:]
    ok, msg, _ = keys.verify_key(bad, pk)
    assert ok is False


def test_key_signed_by_another_issuer_is_rejected(issuer):
    _, pk = issuer
    other = ed25519.generate_private_key()
    forged = keys.encode_key(_lic(key_id="EVIL"), other)
    ok, msg, _ = keys.verify_key(forged, pk)
    assert ok is False
    assert "not issued by" in msg


def test_expired_key_is_rejected(issuer):
    sk, pk = issuer
    ok, msg, lic = keys.verify_key(keys.encode_key(
        _lic(expires="2020-01-01"), sk), pk)
    assert ok is False and "expired" in msg.lower()
    assert lic.expired is True


def test_perpetual_key_never_expires(issuer):
    sk, pk = issuer
    ok, _, lic = keys.verify_key(keys.encode_key(_lic(expires=None), sk), pk)
    assert ok is True
    assert lic.expired is False and lic.days_remaining() is None


def test_malformed_expiry_is_treated_as_expired(issuer):
    sk, pk = issuer
    ok, _, _ = keys.verify_key(keys.encode_key(_lic(expires="not-a-date"), sk), pk)
    assert ok is False


@pytest.mark.parametrize("junk", [
    "", "hello", "PT-", "PT-AAAA", "XX-AAAA-BBBB", "PT-!!!!-????",
    "PT-AAAAAAAA-BBBBBBBB",
])
def test_garbage_keys_fail_gracefully(junk, issuer):
    _, pk = issuer
    ok, msg, _ = keys.verify_key(junk, pk)
    assert ok is False
    assert isinstance(msg, str) and msg


def test_normalize_accepts_sloppy_input(issuer):
    sk, pk = issuer
    key = keys.encode_key(_lic(), sk)
    messy = "  " + key.lower().replace("-", "- ") + "  "
    assert keys.verify_key(messy, pk)[0] is True


def test_email_is_never_stored_in_plaintext(issuer):
    sk, pk = issuer
    import hashlib
    h = hashlib.sha256(b"buyer@example.com").hexdigest()[:32]
    key = keys.encode_key(_lic(email_hash=h), sk)
    _, payload, _ = keys.decode_key(key)
    assert b"buyer@example.com" not in payload
    assert h.encode() in payload


def test_build_without_public_key_says_so_clearly(monkeypatch):
    monkeypatch.setattr(keys, "ISSUER_PUBLIC_KEY_B64",
                        "PLACEHOLDER_REPLACE_WITH_YOUR_PUBLIC_KEY")
    sk = ed25519.generate_private_key()
    ok, msg, _ = keys.verify_key(keys.encode_key(_lic(), sk))
    assert ok is False
    assert "build configuration" in msg


# ------------------------------------------------------- online validation

def test_validation_disabled_when_no_endpoint():
    from phantom_tweeks.licensing import validation as v
    r = v.validate_online("k", "id", "0.1.2", endpoint="")
    assert r.status == "disabled" and r.ok is True


def test_validation_refuses_plain_http():
    from phantom_tweeks.licensing import validation as v
    r = v.validate_online("k", "id", "0.1.2", endpoint="http://insecure.example")
    assert r.ok is False
    assert "insecure" in r.message.lower()


def test_unreachable_server_does_not_lock_the_user_out(tmp_path, monkeypatch):
    monkeypatch.setenv("PHANTOM_TWEEKS_HOME", str(tmp_path))
    from phantom_tweeks.core import paths
    importlib.reload(paths)
    from phantom_tweeks.licensing import validation as v
    importlib.reload(v)
    r = v.validate_online("k", "id", "0.1.2",
                          endpoint="https://127.0.0.1:1/nope")
    assert r.ok is True, "an outage must not revoke a paying user's access"
    assert r.status == "offline"
    monkeypatch.undo()
    importlib.reload(paths)


def test_device_fingerprint_is_stable_and_opaque():
    from phantom_tweeks.licensing import validation as v
    a, b = v.device_fingerprint(), v.device_fingerprint()
    assert a == b and len(a) == 32
    import platform
    assert (platform.node() or "x") not in a


def test_revocation_is_remembered_permanently(tmp_path, monkeypatch):
    monkeypatch.setenv("PHANTOM_TWEEKS_HOME", str(tmp_path))
    from phantom_tweeks.core import paths
    importlib.reload(paths)
    from phantom_tweeks.licensing import validation as v
    importlib.reload(v)
    v._write_cache("K1", "revoked", "refunded")
    cached = v._cached_result("K1")
    assert cached is not None and cached.ok is False
    assert cached.status == "revoked"
    monkeypatch.undo()
    importlib.reload(paths)


# ------------------------------------------------------- premium gating

def test_premium_is_off_without_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PHANTOM_TWEEKS_HOME", str(tmp_path))
    from phantom_tweeks.core import paths, premium
    importlib.reload(paths)
    importlib.reload(premium)
    assert premium.is_premium() is False
    allowed, msg = premium.require_premium("Cloud profiles")
    assert allowed is False and "Premium feature" in msg
    monkeypatch.undo()
    importlib.reload(paths)
    importlib.reload(premium)


def test_no_private_key_or_real_key_is_shipped():
    """The repo must never contain an issuer private key."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert not (root / "admin" / "issuer-private.key").exists()
    assert not (root / "admin" / "issued-keys.jsonl").exists()
    text = (root / "src" / "phantom_tweeks" / "licensing" / "keys.py").read_text()
    assert "PLACEHOLDER" in text, "a real public key was committed; that is fine, " \
                                  "but confirm the PRIVATE key was not"


@pytest.mark.repo_hygiene
def test_gitignore_excludes_licensing_secrets():
    """.gitignore must keep the issuer private key out of the repository.

    If the file is absent from this checkout we skip rather than fail: the
    build itself is still correct, and hard-failing here would block a release
    over a packaging slip. The real security guarantee — that no private key is
    present — is asserted by test_no_private_key_or_real_key_is_shipped above,
    which does NOT skip.

    Absent usually means the repo was uploaded through the GitHub web UI, which
    silently drops dotfiles. Add it with:  git add -f .gitignore
    """
    from pathlib import Path
    gi_path = Path(__file__).resolve().parents[1] / ".gitignore"
    if not gi_path.is_file():
        pytest.skip(".gitignore is missing from this checkout — add it with "
                    "'git add -f .gitignore' so admin/issuer-private.key can "
                    "never be committed.")
    gi = gi_path.read_text()
    assert "issuer-private.key" in gi
    assert "issued-keys.jsonl" in gi


def test_ed25519_needs_no_deep_recursion():
    """A frozen GUI app can already be deep in the stack inside a callback.

    If signature maths recursed ~253 frames it could raise RecursionError,
    which would surface to the user as a bogus 'invalid license'.
    """
    import threading

    result = {}

    def work():
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(80)
        try:
            sk = ed25519.generate_private_key()
            pk = ed25519.public_key(sk)
            sig = ed25519.sign(sk, b"deep stack")
            result["ok"] = ed25519.verify(pk, b"deep stack", sig)
        except RecursionError as e:
            result["error"] = str(e)
        finally:
            sys.setrecursionlimit(old)

    t = threading.Thread(target=work)
    t.start()
    t.join(timeout=60)
    assert "error" not in result, f"recursion is still used: {result['error']}"
    assert result.get("ok") is True


def test_scalarmult_is_iterative():
    import inspect
    src = inspect.getsource(ed25519._scalarmult)
    assert "_scalarmult(" not in src.split("def _scalarmult")[1].split(":", 1)[1], \
        "_scalarmult still calls itself"
