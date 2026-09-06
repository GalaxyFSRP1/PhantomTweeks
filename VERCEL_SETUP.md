# Vercel setup — step by step

You need this so the website can (a) serve downloads from your **private** repo
and (b) validate license keys. Total time: about 10 minutes.

---

## Step 0 — Make sure the dotfiles are actually in GitHub

This is what broke your CI run. GitHub's **web uploader silently drops files
whose name starts with a dot**, so `.gitignore`, `.vercelignore` and the whole
`.github/` folder never arrived. Without `.github/workflows/build.yml` there
is no build at all.

Use git from the command line, not drag-and-drop:

```bash
cd path\to\phantom-tweeks
git init
git remote add origin https://github.com/GalaxyFSRP1/PhantomTweeks.git
git add -A
git add -f .gitignore .vercelignore .github
git commit -m "Phantom Tweeks 0.1.2"
git branch -M main
git push -u origin main
```

Verify on github.com that you can see `.github/workflows/build.yml`. If you
cannot, Actions will never run.

---

## Step 1 — Create the GitHub token

The website needs to read release assets from a private repo.

1. GitHub → click your avatar (top right) → **Settings**
2. Scroll to the bottom of the left sidebar → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. Fill in:
   - **Token name:** `phantom-tweeks-website`
   - **Expiration:** 90 days (set a reminder to renew)
   - **Repository access:** *Only select repositories* → `PhantomTweeks`
   - **Permissions** → *Repository permissions* → find **Contents** → set to
     **Read-only**
5. **Generate token** and copy it. You cannot view it again.

> Contents: Read-only is the *only* permission needed. Do not grant write
> access, and do not use a classic token with full `repo` scope.

---

## Step 2 — Import the project into Vercel

1. Go to <https://vercel.com> and sign in **with GitHub**
2. **Add New…** → **Project**
3. Find `GalaxyFSRP1/PhantomTweeks` → **Import**
   - If it is not listed: **Adjust GitHub App Permissions** → grant access to
     the repo
4. On the configure screen:
   - **Framework Preset:** `Other`
   - **Root Directory:** leave as `./`
   - **Build Command:** leave **empty**
   - **Output Directory:** should show `website` (it comes from `vercel.json`)
   - **Install Command:** leave **empty**
5. Do **not** deploy yet — open **Environment Variables** first (next step).

---

## Step 3 — Environment variables

Add these three. Tick **Production**, **Preview** and **Development** for each.

| Name | Value | What it does |
| --- | --- | --- |
| `GITHUB_TOKEN` | the token from Step 1 | Lets the site fetch release files from your private repo |
| `GITHUB_REPO` | `GalaxyFSRP1/PhantomTweeks` | Which repo to read |
| `PHANTOM_PUBLIC_KEY` | output of `python admin/admin_cli.py genkey` | Verifies license keys |

For `PHANTOM_PUBLIC_KEY`, run locally:

```bash
python admin/admin_cli.py genkey
```

Copy the **Public key** line (the base64 string). Never paste the *private*
key anywhere — it stays on your machine only.

Now click **Deploy**.

---

## Step 4 — Check it works

Replace `your-domain` with the URL Vercel gives you.

| URL | Expected |
| --- | --- |
| `https://your-domain/` | The Phantom Tweeks homepage |
| `https://your-domain/api/health` | `"public_key_configured": true` |
| `https://your-domain/api/latest` | Your release version + checksums |
| `https://your-domain/api/download?file=setup` | Downloads the installer |

If `/api/latest` says *"No release has been published yet"*, that is correct
until you push a tag — do Step 5.

If `/api/health` says `public_key_configured: false`, `PHANTOM_PUBLIC_KEY` did
not save. Re-add it and **redeploy** (env var changes need a new deployment).

---

## Step 5 — Cut a release

```bash
git tag v0.1.2
git push origin v0.1.2
```

Watch the **Actions** tab. When it goes green, the Release appears with all
three `.exe` files attached, and `/api/latest` starts reporting them
automatically. The download page updates itself — no code change needed.

---

## Troubleshooting

**Actions never runs** — `.github/` was not uploaded. See Step 0.

**404 on `/api/...`** — `vercel.json` was not uploaded, or Output Directory is
not `website`. Check Project → Settings → General.

**`/api/download` returns "not configured"** — `GITHUB_TOKEN` is missing or
expired. Fine-grained tokens expire; regenerate and update the variable.

**`/api/download` returns 404 "asset_missing"** — no release published yet, or
the tag build failed. Check the Actions tab.

**Site deploys but is blank** — Output Directory is wrong. It must be `website`.

---

## Cost

Everything here fits Vercel's free Hobby tier. The one thing to watch is
**bandwidth**: each download of a ~30 MB installer counts against your monthly
allowance (100 GB on Hobby ≈ 3,300 downloads). If you outgrow that, switch the
buttons to point directly at GitHub Releases and make the repo public, or move
the binaries to R2/B2 object storage.

---

## Troubleshooting the live site

### The download button gives "502 Bad Gateway"

This was a bug in `api/download.py` and is fixed. The underlying cause was
almost always **no GitHub Release existed yet** — the endpoint tried to look up
an asset, GitHub answered 404, and the function returned a bare 502 that
Cloudflare rendered as its generic error page.

The endpoint now answers with an explanation instead, and the download page
disables its buttons until a release actually exists. To make downloads work:

```powershell
git tag -f v0.1.2
git push -f origin v0.1.2
```

Wait for the workflow to finish, then confirm a release exists at
`/releases`. `/api/latest` should then report `"available": true`.

### `/api/latest` returns 404 in the browser console

Also fixed. "No release yet" is a normal state for a new site, so the endpoint
now returns **200** with `"available": false` rather than a 404 that shows up
as a red console error.

### Checking the deployment yourself

```bash
curl -s https://<your-domain>/api/health        # public_key_configured: true
curl -s https://<your-domain>/api/latest        # available: true/false
curl -sI https://<your-domain>/api/download?file=setup
```

`/api/health` returning 200 proves the Python functions are deploying. If
`health` works but `download` fails, the problem is the token or the release,
not the deployment.

### "Downloads are not configured yet" (503)

`GITHUB_TOKEN` is missing from the Vercel project. Add a fine-grained PAT
scoped to this repository with **Contents: Read-only**, then redeploy — Vercel
does not apply new environment variables to an existing deployment.
