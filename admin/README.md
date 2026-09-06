# Phantom Tweeks — Admin / Key Issuing

**Everything in this folder is for YOU, the publisher. Never ship it to users
and never commit the private key.** `.gitignore` already excludes
`issuer-private.key` and `issued-keys.jsonl`.

## 1. Create your issuer keypair (once)

```
python admin/admin_cli.py genkey
```

Writes `admin/issuer-private.key` (KEEP SECRET, back it up offline) and prints
the matching public key.

- Lose the private key → you cannot issue or renew keys. Existing keys keep working.
- Leak the private key → anyone can mint licenses. Rotate and re-issue.

## 2. Embed the public key in the client

```
python admin/admin_cli.py install-pubkey
```

The public key is safe to embed and publish. Only the private key can sign.
Rebuild the EXE after doing this.

## 3. Issue a license

```
python admin/admin_cli.py issue --plan premium  --days 365 --email buyer@example.com
python admin/admin_cli.py issue --plan lifetime
python admin/admin_cli.py issue --plan trial    --days 14
```

Each key is appended to `admin/issued-keys.jsonl`. Email addresses are stored
only as a truncated SHA-256 hash, never in plain text.

## 4. Verify, inspect, list

```
python admin/admin_cli.py verify  PT-XXXX-...
python admin/admin_cli.py inspect PT-XXXX-...
python admin/admin_cli.py list
```

## 5. Revoke

```
python admin/admin_cli.py revoke C1E1FC85972C --reason "refunded"
python admin/admin_cli.py unrevoke C1E1FC85972C
```

Writes `admin/revoked.json`, which the Vercel API reads. Copy it to
`api/revoked.json` (or set the `REVOKED_KEYS` env var) and redeploy.

**Honest limitation:** revocation only reaches clients that can contact your
server. An offline client keeps working until its cached status expires (14
days). No client-side scheme can do better without locking out legitimate
offline users.
