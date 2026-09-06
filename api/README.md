# Serverless licensing API

Two Vercel Python functions. No dependencies, no build step — they import the
licensing code from `../src`.

- `validate.py` → `POST /api/validate` with `{"key": "PT-..."}`.
  Responds `{"status": "valid|invalid|expired|revoked|unknown", "message": "..."}`
- `health.py` → `GET /api/health`, confirms `PHANTOM_PUBLIC_KEY` is configured.

Required environment variable: `PHANTOM_PUBLIC_KEY` (base64 Ed25519 **public**
key). Never deploy the private key.

Optional: `REVOKED_KEYS` — comma-separated key ids to reject.

See `../DEPLOYMENT.md` for full setup.
