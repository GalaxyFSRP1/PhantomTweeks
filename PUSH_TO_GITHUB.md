# Pushing to GitHub — start here

## The error you hit

```
fatal: not a git repository (or any of the parent directories): .git
```

This just means `D:\phantom-tweeks` is a plain folder, not a git repository
yet. `git add` needs a repository to add *to*. Nothing is broken — you only
need to run `git init` first, which is a one-time step.

---

## Easiest way: use the script

From `D:\phantom-tweeks`:

```powershell
.\push-to-github.ps1
```

It initialises git if needed, force-adds the dotfiles, refuses to continue if
`admin\issuer-private.key` is present, verifies the dotfiles really made it
into the commit, and pushes.

To push **and** cut a release in one go:

```powershell
.\push-to-github.ps1 -Tag v0.1.2
```

---

## Or do it by hand

Run these one at a time from `D:\phantom-tweeks`:

```powershell
git init
git branch -M main
git remote add origin https://github.com/GalaxyFSRP1/PhantomTweeks.git

git add -A
git add -f .gitignore .vercelignore .github

git commit -m "Phantom Tweeks 0.1.2"
git push -u origin main
```

If `git init` says git is not recognised, install it from
<https://git-scm.com/download/win> and reopen your terminal.

If `git remote add` says *"remote origin already exists"*, use this instead:

```powershell
git remote set-url origin https://github.com/GalaxyFSRP1/PhantomTweeks.git
```

### Signing in

On first push a browser window opens for GitHub sign-in. If you are asked for a
password at the terminal instead, GitHub no longer accepts account passwords —
create a Personal Access Token (Settings → Developer settings → Tokens) and
paste that as the password.

---

## Verify it worked

**This is the step that has bitten us twice.** After pushing, open
<https://github.com/GalaxyFSRP1/PhantomTweeks> and confirm you can see a
`.github` folder with `workflows/build.yml` inside it.

If it is not there, GitHub Actions will never run and no `.exe` will ever be
built. Fix it with:

```powershell
git add -f .github
git commit -m "Add CI workflow"
git push
```

Why this keeps happening: **GitHub's drag-and-drop web uploader silently skips
files and folders whose name begins with a dot.** Pushing with git from the
command line does not have this limitation.

Quick check from the terminal — this should list all three files:

```powershell
git ls-files .gitignore .vercelignore .github/workflows/build.yml
```

---

## If PowerShell refuses to run the script

**"cannot be loaded because running scripts is disabled on this system"** —
Windows blocks local scripts by default. Allow them for your account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Or run it once without changing any setting:

```powershell
powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1
```

**"The string is missing the terminator"** — two separate bugs in earlier
copies of this script caused that, both now fixed:

1. Unix (LF) line endings, which break here-string terminators.
2. A single em dash character. Windows PowerShell 5.1 reads a file without a
   byte-order mark as cp1252, and in that encoding part of a UTF-8 em dash
   becomes a smart quote, which PowerShell treats as the start of a string.
   The error is then reported at the *last line of the file*, nowhere near
   the actual cause.

The scripts are now pure ASCII, CRLF, and BOM-prefixed, and tests enforce all
three. If you ever see this again, re-extract from the zip rather than
copy-pasting the script out of a browser or chat window, which can silently
substitute smart quotes and dashes.

---

## "Updates were rejected because the remote contains work you do not have"

Your GitHub repo has commits that your local folder does not - almost
certainly the earlier partial uploads made through the website. Git refuses to
overwrite them without being told to. **Nothing has been changed on GitHub at
this point.**

Your local folder is the complete, tested copy, and the website uploads are
the broken ones we have been trying to replace. So in this case you want your
local version to win:

```powershell
.\push-to-github.ps1 -Force
```

Before overwriting anything, this saves the current remote state to a branch
named `backup-before-force-<timestamp>`, so the old uploads remain recoverable
on GitHub even after the force push. It uses `--force-with-lease`, which
aborts if the remote changed since it last checked, rather than blindly
clobbering it.

**Only if** you edited files directly on github.com and want to keep those
edits, merge instead:

```powershell
git pull --rebase origin main
.\push-to-github.ps1
```

To see what is actually on the remote before deciding:

```powershell
git fetch origin
git log --oneline origin/main
```

---

## Never commit the private key

`admin\issuer-private.key` signs your license keys. If it leaks, anyone can
mint licenses for your product.

`.gitignore` already excludes it, and `push-to-github.ps1` refuses to run if it
is present. To confirm nothing sensitive is tracked:

```powershell
git ls-files | Select-String "issuer-private"
```

That must return nothing.

---

## Updating later

After the first setup you only need:

```powershell
git add -A
git commit -m "What changed"
git push
```

And to release a new version:

```powershell
git tag v0.1.3
git push origin v0.1.3
```
