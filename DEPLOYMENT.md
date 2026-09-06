# Deploying Phantom Tweeks to Vercel

Repo: `https://github.com/GalaxyFSRP1/PhantomTweeks` (private)

## What Vercel serves

| Path in repo | Becomes |
| --- | --- |
| `website/` | the static site (this is the **Output Directory**) |
| `api/validate.py` | `POST https://<your-domain>/api/validate` |
| `api/health.py` | `GET  https://<your-domain>/api/health` |

`vercel.json` in the repo root already declares all of this, so Vercel does not
need to guess. The key line is `"outputDirectory": "website"` — without it
Vercel looks for `index.html` in the repo root and deploys a blank site.

## First-time setup

1. Push this repo to GitHub (private is fine — Vercel supports private repos).
2. In Vercel: **Add New → Project → Import** `GalaxyFSRP1/PhantomTweeks`.
3. Framework Preset: **Other**. Leave Build Command and Install Command **empty**.
   Output Directory should auto-fill from `vercel.json` as `website`.
4. Add an Environment Variable:

   | Name | Value |
   | --- | --- |
   | `PHANTOM_PUBLIC_KEY` | the base64 public key from `python admin/admin_cli.py genkey` |
   | `GITHUB_TOKEN` | fine-grained PAT, **Contents: read** on this repo only |
   | `GITHUB_REPO` | `GalaxyFSRP1/PhantomTweeks` |

   `GITHUB_TOKEN` is what lets the website serve downloads from a **private**
   repo — see `RELEASING.md`.

   Add it for Production, Preview and Development.
5. Deploy. Check `https://<your-domain>/api/health` — it must report
   `"public_key_configured": true`.

## Point the app at your API

In `src/phantom_tweeks/licensing/validation.py` set:

```python
VALIDATION_ENDPOINT = "https://your-domain.vercel.app/api"
```

Then rebuild the EXE. Leaving it empty is valid: keys are still verified
offline by signature, you just get no revocation.

## Revoking keys

```
python admin/admin_cli.py revoke ABCDEF123456 --reason "chargeback"
```

Then either commit `admin/revoked.json` to `api/revoked.json` and redeploy, or
paste the ids into the `REVOKED_KEYS` environment variable in Vercel
(comma-separated) — the env var needs no redeploy of code, just a
redeploy/restart.

## Security checklist before going live

- [ ] `admin/issuer-private.key` is **not** in the repo (`.gitignore` covers it)
- [ ] `PHANTOM_PUBLIC_KEY` is set in Vercel (the *public* key only)
- [ ] `/api/health` reports `public_key_configured: true`
- [ ] The download page lists the real SHA-256 values from `dist/SHA256SUMS.txt`
- [ ] The EXE is code-signed (otherwise SmartScreen blocks your users)

## Honest limits of this licensing scheme

Offline signature verification stops users **inventing** keys. It does not stop
someone patching the binary to skip the check — no client-side scheme does.
Online validation adds revocation, which is what actually limits key sharing.
If your server is unreachable, a previously valid key keeps working for 14 days
rather than locking out a paying customer during your outage.
