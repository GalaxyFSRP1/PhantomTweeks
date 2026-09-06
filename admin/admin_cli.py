#!/usr/bin/env python3
"""Phantom Tweeks admin tool — issue, verify and revoke license keys.

PUBLISHER ONLY. Do not distribute this file or the private key it creates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

sys.setrecursionlimit(10000)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from phantom_tweeks.licensing import ed25519, keys   # noqa: E402

PRIVATE_KEY_FILE = HERE / "issuer-private.key"
ISSUED_LOG = HERE / "issued-keys.jsonl"
REVOKED_FILE = HERE / "revoked.json"


def _load_private() -> bytes:
    if not PRIVATE_KEY_FILE.exists():
        sys.exit("No issuer key found. Run: python admin/admin_cli.py genkey")
    import base64
    return base64.b64decode(PRIVATE_KEY_FILE.read_text().strip())


def cmd_genkey(args) -> int:
    import base64
    if PRIVATE_KEY_FILE.exists() and not args.force:
        sys.exit(f"{PRIVATE_KEY_FILE} already exists. Use --force to overwrite "
                 "(this INVALIDATES your ability to issue matching keys).")
    sk = ed25519.generate_private_key()
    pk = ed25519.public_key(sk)
    PRIVATE_KEY_FILE.write_text(base64.b64encode(sk).decode())
    try:
        os.chmod(PRIVATE_KEY_FILE, 0o600)
    except OSError:
        pass
    pub_b64 = base64.b64encode(pk).decode()
    print("Issuer keypair created.\n")
    print(f"  Private key : {PRIVATE_KEY_FILE}  (SECRET — back up offline)")
    print(f"  Public key  : {pub_b64}\n")
    print("Next: python admin/admin_cli.py install-pubkey")
    return 0


def cmd_install_pubkey(args) -> int:
    import base64
    sk = _load_private()
    pub_b64 = base64.b64encode(ed25519.public_key(sk)).decode()
    target = HERE.parent / "src" / "phantom_tweeks" / "licensing" / "keys.py"
    text = target.read_text(encoding="utf-8")
    import re
    new = re.sub(r'ISSUER_PUBLIC_KEY_B64 = "[^"]*"',
                 f'ISSUER_PUBLIC_KEY_B64 = "{pub_b64}"', text, count=1)
    if new == text:
        sys.exit("Could not find ISSUER_PUBLIC_KEY_B64 to replace.")
    target.write_text(new, encoding="utf-8")
    print(f"Embedded public key into {target.relative_to(HERE.parent)}")
    return 0


def cmd_issue(args) -> int:
    sk = _load_private()
    key_id = secrets.token_hex(6).upper()
    expires = None
    if args.days:
        expires = (date.today() + timedelta(days=args.days)).isoformat()
    email_hash = None
    if args.email:
        email_hash = hashlib.sha256(args.email.strip().lower()
                                    .encode()).hexdigest()[:32]
    lic = keys.LicenseKey(
        key_id=key_id, plan=args.plan, issued=date.today().isoformat(),
        expires=expires, device_id=args.device, seats=args.seats,
        email_hash=email_hash, note=args.note or "")
    key = keys.encode_key(lic, sk)

    with ISSUED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"key_id": key_id, "plan": args.plan,
                            "issued": lic.issued, "expires": expires,
                            "email_hash": email_hash, "note": args.note or "",
                            "key": key}) + "\n")

    print(f"\nPlan     : {args.plan}")
    print(f"Key ID   : {key_id}")
    print(f"Expires  : {expires or 'never'}")
    print(f"\n{key}\n")
    print(f"Logged to {ISSUED_LOG.name}")
    return 0


def cmd_verify(args) -> int:
    import base64
    sk = _load_private()
    pub = ed25519.public_key(sk)
    ok, msg, lic = keys.verify_key(args.key, pub)
    print(("VALID   " if ok else "INVALID ") + msg)
    if lic:
        print(f"  key_id  {lic.key_id}\n  plan    {lic.plan}\n"
              f"  issued  {lic.issued}\n  expires {lic.expires or 'never'}")
    return 0 if ok else 1


def cmd_inspect(args) -> int:
    try:
        lic, payload, sig = keys.decode_key(args.key)
    except keys.KeyError_ as e:
        sys.exit(str(e))
    print(json.dumps(lic.__dict__, indent=2))
    print(f"\npayload {len(payload)} bytes, signature {len(sig)} bytes")
    print("NOTE: inspect does not verify the signature. Use 'verify'.")
    return 0


def _revoked() -> dict:
    if REVOKED_FILE.exists():
        try:
            return json.loads(REVOKED_FILE.read_text())
        except Exception:
            return {}
    return {}


def cmd_revoke(args) -> int:
    data = _revoked()
    data[args.key_id.upper()] = {
        "reason": args.reason or "unspecified",
        "at": date.today().isoformat(),
    }
    REVOKED_FILE.write_text(json.dumps(data, indent=2))
    print(f"Revoked {args.key_id}. {len(data)} key(s) on the revocation list.")
    print("Deploy the website/API for this to take effect for online clients.")
    return 0


def cmd_unrevoke(args) -> int:
    data = _revoked()
    if data.pop(args.key_id.upper(), None) is None:
        print(f"{args.key_id} was not revoked.")
        return 1
    REVOKED_FILE.write_text(json.dumps(data, indent=2))
    print(f"Restored {args.key_id}.")
    return 0


def cmd_list(args) -> int:
    if not ISSUED_LOG.exists():
        print("No keys issued yet.")
        return 0
    revoked = _revoked()
    rows = [json.loads(l) for l in ISSUED_LOG.read_text().splitlines() if l.strip()]
    print(f"{'KEY ID':14}{'PLAN':12}{'ISSUED':12}{'EXPIRES':12}STATUS")
    for r in rows:
        status = "REVOKED" if r["key_id"] in revoked else "active"
        print(f"{r['key_id']:14}{r['plan']:12}{r['issued']:12}"
              f"{str(r['expires'] or 'never'):12}{status}")
    print(f"\n{len(rows)} key(s), {len(revoked)} revoked.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Phantom Tweeks license admin")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("genkey", help="create the issuer keypair")
    g.add_argument("--force", action="store_true")
    g.set_defaults(fn=cmd_genkey)

    sub.add_parser("install-pubkey",
                   help="embed the public key into the client").set_defaults(
        fn=cmd_install_pubkey)

    i = sub.add_parser("issue", help="issue a new license key")
    i.add_argument("--plan", default="premium",
                   choices=["premium", "lifetime", "trial"])
    i.add_argument("--days", type=int, default=None,
                   help="validity in days (omit for perpetual)")
    i.add_argument("--email", default=None, help="stored only as a hash")
    i.add_argument("--device", default=None, help="bind to a device id")
    i.add_argument("--seats", type=int, default=1)
    i.add_argument("--note", default="")
    i.set_defaults(fn=cmd_issue)

    v = sub.add_parser("verify", help="verify a key against your public key")
    v.add_argument("key")
    v.set_defaults(fn=cmd_verify)

    n = sub.add_parser("inspect", help="decode a key without verifying")
    n.add_argument("key")
    n.set_defaults(fn=cmd_inspect)

    r = sub.add_parser("revoke", help="add a key to the revocation list")
    r.add_argument("key_id")
    r.add_argument("--reason", default="")
    r.set_defaults(fn=cmd_revoke)

    u = sub.add_parser("unrevoke", help="remove a key from the revocation list")
    u.add_argument("key_id")
    u.set_defaults(fn=cmd_unrevoke)

    sub.add_parser("list", help="list issued keys").set_defaults(fn=cmd_list)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
