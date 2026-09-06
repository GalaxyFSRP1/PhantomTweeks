# Automatic builds, releases and website downloads

Three pieces work together:

1. **GitHub Actions** builds the `.exe` files on a Windows runner and attaches
   them to a GitHub Release.
2. **`/api/download`** streams those files to the public, because your repo is
   private and release assets on a private repo are *not* publicly downloadable.
3. **`/api/latest`** feeds the real version, file sizes and SHA-256 checksums
   into the download page so nothing is hard-coded and stale.

---

## Part 1 — Automatic builds

`.github/workflows/build.yml` is already in the repo. Nothing to configure: it
uses the `GITHUB_TOKEN` that Actions provides automatically.

| Trigger | What happens |
| --- | --- |
| Push to `main` | Builds and uploads artifacts (30-day retention). No release. |
| Pull request | Same — catches breakage before merge. |
| Push a tag `v*` | Builds **and publishes a GitHub Release** with all binaries. |
| Actions tab → Run workflow | Manual build whenever you want. |

The workflow installs Python and Inno Setup, runs `.\build.ps1` (which runs the
full test suite and refuses to build from a failing tree), then **smoke-tests
the produced EXE** by running `PhantomTweeks.exe version`. That last step exists
because a binary that compiles but cannot start is exactly the bug your friend
hit — CI now fails loudly instead of shipping it.

### Cutting a release

```bash
# 1. Set the version in src/phantom_tweeks/branding.py (and the other spots)
# 2. Commit
git add -A && git commit -m "Release 0.2.1"

# 3. Tag and push
git tag v0.2.1
git push origin main
git push origin v0.2.1
```

Watch it under the **Actions** tab. When it finishes, the release appears under
**Releases** with `PhantomTweeks-Setup.exe`, `PhantomTweeks.exe`,
`PhantomTweeks-Portable.exe` and `SHA256SUMS.txt` attached.

Versions starting `0.` are automatically marked **pre-release**.

---

## Part 2 — Making downloads work on a private repo

This is the part that trips people up. A link like
`https://github.com/GalaxyFSRP1/PhantomTweeks/releases/download/v0.2.1/PhantomTweeks-Setup.exe`
returns **404 for everyone except you** while the repo is private. Your visitors
would see a broken download.

`api/download.py` solves it: it holds a token server-side, fetches the asset
from GitHub, and streams it back. The token never reaches the browser.

### Create the token

1. GitHub → your avatar → **Settings** → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
2. **Repository access:** Only select repositories → `PhantomTweeks`
3. **Permissions:** Repository permissions → **Contents: Read-only**
   (that is the only permission needed)
4. Set an expiry you will actually remember to renew. Copy the token.

### Add it to Vercel

Project → **Settings** → **Environment Variables**:

| Name | Value | Environments |
| --- | --- | --- |
| `GITHUB_TOKEN` | the fine-grained token | Production, Preview, Development |
| `GITHUB_REPO` | `GalaxyFSRP1/PhantomTweeks` | all three |
| `PHANTOM_PUBLIC_KEY` | your licensing public key | all three |

Redeploy. Then check:

- `https://your-domain/api/latest` → should show your version and checksums
- `https://your-domain/api/download?file=setup` → should download the installer

### The alternative

If you would rather not run a proxy, make the repo **public**. Release assets on
a public repo are directly downloadable and you can point the buttons straight
at `github.com/.../releases/latest/download/PhantomTweeks-Setup.exe`. Your source
would then be public — that is the trade.

---

## Part 3 — The download page

`website/download.html` now links to `/api/download?file=setup` and
`?file=portable`, and fetches `/api/latest` on load to fill in the real version,
file sizes and SHA-256 hashes.

If no release exists yet, the page says so plainly instead of showing a broken
button. If the API is unreachable it keeps the static text. Nothing pretends a
download exists when it does not.

---

## Before you share it publicly

- [ ] Push a `v*` tag and confirm the Actions run goes green
- [ ] Confirm `/api/latest` returns your version
- [ ] Download through `/api/download?file=setup` and check the SHA-256 matches
- [ ] **Code-sign the binaries.** Unsigned executables trigger SmartScreen and
      give users no way to verify what they are running. To sign in CI, add your
      certificate as a secret and pass `-Sign -CertThumbprint` to `build.ps1`.
- [ ] Confirm `admin/issuer-private.key` is not in the repo

## Signing in CI (when you have a certificate)

Store the `.pfx` base64-encoded as the secret `SIGNING_CERT` and its password as
`SIGNING_PASSWORD`, then add a step before the build that imports it and pass
the thumbprint to `build.ps1`. Until then the workflow builds unsigned binaries
and the release notes say so honestly.

---

## The MSI package

`build.ps1` now produces **two** installers, because they serve different needs:

| File | Use it for |
| --- | --- |
| `PhantomTweeks-Setup.exe` | Normal users. Friendly wizard, made by Inno Setup. |
| `PhantomTweeks-0.2.1.msi` | Managed deployment — Group Policy, Intune, SCCM, or `msiexec`. |

An `.msi` is a real Windows Installer database, which is what corporate
deployment tools require; they cannot script an arbitrary `.exe` reliably.

### Building it

Requires the WiX Toolset, **pinned to 5.0.2**:

```powershell
dotnet tool install --global wix --version 5.0.2
```

> **Do not install WiX unpinned.** WiX v6 introduced the Open Source
> Maintenance Fee, and v7 enforces it by refusing to run any command until
> you accept the OSMF EULA (`error WIX7015`). Version 5.0.2 is the last
> release without that requirement, and it compiles our WiX v4-schema
> `.wxs` without changes.
>
> The fee applies to organisations generating revenue from WiX (v7 added a
> US$10,000 annual revenue threshold). If Phantom Tweeks starts earning and
> you want to move to v7, review <https://wixtoolset.org/osmf/> and accept
> with `wix eula accept wix7`. That is a licensing decision, so it is left
> to you rather than automated in the build.

Then `.\build.ps1` picks it up automatically. If WiX is not installed the MSI
is **skipped with a warning** and the `.exe` installer is still produced — a
missing optional tool never fails the build. Skip it explicitly with
`.\build.ps1 -SkipMsi`.

CI installs WiX and verifies the result is a genuine installer database by
checking its OLE compound-document magic bytes (`D0CF11E0A1B11AE1`), not just
the file extension.

### Installing from the command line

```powershell
msiexec /i PhantomTweeks-0.2.1.msi                  # normal install
msiexec /i PhantomTweeks-0.2.1.msi /quiet /norestart  # silent
msiexec /i PhantomTweeks-0.2.1.msi INSTALLDESKTOPSHORTCUT=0   # no desktop icon
msiexec /x PhantomTweeks-0.2.1.msi                  # uninstall
```

### What it installs

`PhantomTweeks.exe`, the icon, and the PRIVACY / SECURITY / USER_GUIDE / EULA
documents into `C:\Program Files\Phantom Tweeks`, plus a Start-menu shortcut
and (by default) a desktop shortcut.

Adding Phantom Tweeks to `PATH` is an **optional feature, off by default** —
the MSI does not modify your system PATH unless you ask it to.

**Uninstalling never deletes your backups.** Optimization history in
`%LOCALAPPDATA%\PhantomTweeks` is deliberately preserved, so you can reinstall
and still use RESTORE EVERYTHING. A test enforces this.


---

## Publishing a release

The workflow builds on **every push**, but only creates a **GitHub Release**
when you push a **version tag**. A normal `git push` gives you build artifacts
(under the run's "Artifacts" section, kept 90 days); a tag gives you a public
Release with permanent download links.

```powershell
git tag v0.2.1
git push origin v0.2.1
```

Or in one step with the helper:

```powershell
.\push-to-github.ps1 -Tag v0.2.1
```

If the tag already exists on the remote from an earlier attempt, replace it:

```powershell
git tag -d v0.2.1
git push origin :refs/tags/v0.2.1
git tag v0.2.1
git push origin v0.2.1
```

Because the version is `0.x`, the workflow marks the Release as a
**pre-release** automatically. That is intentional: it signals the software is
not yet considered stable. It becomes a normal release at `1.0.0`.

### Where the files go

| Trigger | Result |
| --- | --- |
| Push to `main` | Artifacts on the workflow run only (expire after 90 days) |
| Push a `v*` tag | A GitHub Release with permanent, publicly linkable downloads |
| Manual run (Actions tab) | Artifacts only |
