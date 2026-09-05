"""Minimal Ed25519 (RFC 8032) in pure Python.

Why not a library: the client must verify license signatures while frozen by
PyInstaller, and adding a compiled crypto dependency to a GUI app is a large
cost for ~120 lines of well-specified maths. This is the RFC 8032 reference
algorithm, checked against the official test vectors in tests/test_licensing.py.

Security notes
--------------
* Only the PUBLIC key ships in the client. Signing requires the private key,
  which lives solely on the admin/issuer side. A cracked client cannot mint
  keys; it can only be patched to skip the check, which no scheme prevents.
* This implementation is NOT constant-time. That is acceptable for *verifying*
  public signatures, which involves no secret data. Key generation and signing
  are intended for offline admin use, not for a hostile shared host.
"""
from __future__ import annotations

import hashlib
import os

# Curve parameters (RFC 8032, edwards25519)
P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def _sha512_int(b: bytes) -> int:
    return int.from_bytes(_sha512(b), "little")


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _x_recover(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * I) % P
    if x % 2 != 0:
        x = P - x
    return x


BY = 4 * _inv(5) % P
BX = _x_recover(BY)
B = (BX % P, BY % P, 1, BX * BY % P)

IDENT = (0, 1, 1, 0)


def _edwards_add(pt1, pt2):
    # Extended homogeneous coordinates (RFC 8032 section 5.1.4)
    x1, y1, z1, t1 = pt1
    x2, y2, z2, t2 = pt2
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = t1 * 2 * D * t2 % P
    dd = z1 * 2 * z2 % P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _edwards_double(pt):
    return _edwards_add(pt, pt)


def _scalarmult(pt, e: int):
    """Double-and-add, written iteratively.

    The RFC reference version recurses once per bit (~253 frames). That is
    fine standalone, but this runs inside Tk callbacks in a frozen app where
    the stack is already deep, so a RecursionError would surface as a bogus
    "invalid license". Iteration removes the failure mode entirely.
    """
    if e == 0:
        return IDENT
    result = IDENT
    addend = pt
    while e:
        if e & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_double(addend)
        e >>= 1
    return result


def _encode_point(pt) -> bytes:
    x, y, z, _ = pt
    zi = _inv(z)
    x = x * zi % P
    y = y * zi % P
    return ((y & ~(1 << 255)) | ((x & 1) << 255)).to_bytes(32, "little")


def _decode_point(s: bytes):
    if len(s) != 32:
        raise ValueError("point must be 32 bytes")
    i = int.from_bytes(s, "little")
    y = i & ~(1 << 255)
    sign = i >> 255
    x = _x_recover(y)
    if x & 1 != sign:
        x = P - x
    pt = (x, y, 1, x * y % P)
    if not _is_on_curve(pt):
        raise ValueError("point is not on the curve")
    return pt


def _is_on_curve(pt) -> bool:
    x, y, z, t = pt
    return (z % P != 0
            and x * y % P == z * t % P
            and (y * y - x * x - z * z - D * t * t) % P == 0)


def _secret_expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError("private key must be 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    return a, h[32:]


def generate_private_key() -> bytes:
    """32 cryptographically random bytes from the OS CSPRNG."""
    return os.urandom(32)


def public_key(secret: bytes) -> bytes:
    a, _ = _secret_expand(secret)
    return _encode_point(_scalarmult(B, a))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _secret_expand(secret)
    pub = _encode_point(_scalarmult(B, a))
    r = _sha512_int(prefix + message) % L
    rr = _encode_point(_scalarmult(B, r))
    k = _sha512_int(rr + pub + message) % L
    s = (r + k * a) % L
    return rr + s.to_bytes(32, "little")


def verify(pub: bytes, message: bytes, signature: bytes) -> bool:
    """Return True only for a valid signature. Never raises on bad input."""
    try:
        if len(signature) != 64 or len(pub) != 32:
            return False
        rr = signature[:32]
        s = int.from_bytes(signature[32:], "little")
        if s >= L:                       # reject non-canonical scalars
            return False
        a = _decode_point(pub)
        r_point = _decode_point(rr)
        k = _sha512_int(rr + pub + message) % L
        left = _scalarmult(B, s)
        right = _edwards_add(r_point, _scalarmult(a, k))
        return _encode_point(left) == _encode_point(right)
    except (ValueError, TypeError, OverflowError):
        return False
