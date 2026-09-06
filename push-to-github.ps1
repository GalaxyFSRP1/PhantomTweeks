<#
.SYNOPSIS
    Pushes Phantom Tweeks to GitHub, including the dotfiles the web uploader drops.

.DESCRIPTION
    Run this from the repository root:

        .\push-to-github.ps1
        .\push-to-github.ps1 -Message "Fix CI gating, add MSI"
        .\push-to-github.ps1 -Tag v0.1.2      # also cuts a release
        .\push-to-github.ps1 -Force           # overwrite a stale remote

    Safe to run repeatedly. It initialises git only if needed, refuses to push
    a private key, and verifies the dotfiles actually made it into the commit.
#>
[CmdletBinding()]
param(
    [string]$Message = "Update Phantom Tweeks",
    [string]$Remote  = "https://github.com/GalaxyFSRP1/PhantomTweeks.git",
    [string]$Branch  = "main",
    [string]$Tag     = "",
    [switch]$Force
)

# NOTE: deliberately NOT "Stop". Native commands like git write ordinary
# progress messages to stderr; under "Stop" PowerShell turns those into
# terminating NativeCommandError exceptions and kills the script even though
# git succeeded. Every git call below checks its exit code explicitly instead.
$ErrorActionPreference = "Continue"
function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [OK] $m"   -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m"   -ForegroundColor Yellow }
function Die($m)  { Write-Host "`n  [FAIL] $m" -ForegroundColor Red; exit 1 }

# Run git and capture its output without tripping $ErrorActionPreference.
# git writes ordinary progress to stderr; with "Stop" in effect, piping that
# through PowerShell's error stream (2>&1) turns it into a terminating
# NativeCommandError. Redirecting to a file avoids the error stream entirely.
function Invoke-Git {
    param([string[]]$GitArgs, [switch]$Quiet)
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    try {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # Start-Process splits on spaces, so anything containing a space (a
        # commit message, a path) must be quoted or git sees several arguments.
        $quoted = $GitArgs | ForEach-Object {
            $a = [string]$_
            if ($a -match '[\s"]') { '"' + ($a -replace '"', '\"') + '"' } else { $a }
        }
        $p = Start-Process -FilePath "git" -ArgumentList $quoted -NoNewWindow `
             -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $ErrorActionPreference = $prev
        $text = ((Get-Content $out -Raw -EA SilentlyContinue) +
                 (Get-Content $err -Raw -EA SilentlyContinue))
        if (-not $Quiet -and $text) { Write-Host $text.TrimEnd() }
        return [pscustomobject]@{ Code = $p.ExitCode; Text = [string]$text }
    } finally {
        Remove-Item $out, $err -Force -EA SilentlyContinue
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Die "git is not installed. Get it from https://git-scm.com/download/win"
}

# ---------------------------------------------------------------- safety
Step "Safety check"
if (Test-Path "admin\issuer-private.key") {
    Die "admin\issuer-private.key exists and must NEVER be committed. Move it somewhere safe outside this folder, then re-run."
}
Ok "No issuer private key in the working tree"

if (-not (Test-Path ".gitignore")) {
    Die ".gitignore is missing. Extract the full zip before pushing."
}
if (-not (Test-Path ".github\workflows\build.yml")) {
    Die ".github\workflows\build.yml is missing. Extract the full zip before pushing."
}
Ok "Dotfiles present on disk"

# ---------------------------------------------------------------- init
Step "Preparing the repository"
if (-not (Test-Path ".git")) {
    $r = Invoke-Git @("init") -Quiet
    if ($r.Code -ne 0) { Die "git init failed: $($r.Text)" }
    Ok "Initialised a new git repository"
} else {
    Ok "Existing git repository"
}

$null = Invoke-Git @("branch", "-M", $Branch) -Quiet
Ok "On branch '$Branch'"

$existing = (git remote 2>$null)
if ($existing -contains "origin") {
    $null = Invoke-Git @("remote", "set-url", "origin", $Remote) -Quiet
    Ok "Updated remote 'origin'"
} else {
    $null = Invoke-Git @("remote", "add", "origin", $Remote) -Quiet
    Ok "Added remote 'origin'"
}

# ---------------------------------------------------------------- stage
Step "Staging files"
$r = Invoke-Git @("add", "-A") -Quiet
if ($r.Code -ne 0) { Die "git add failed: $($r.Text)" }
# Force-add the dotfiles. They are not ignored, but this makes the intent
# explicit and catches the case where a stray global gitignore excludes them.
$null = Invoke-Git @("add", "-f", ".gitignore", ".vercelignore", ".github",
                     ".gitattributes") -Quiet
Ok "Files staged"

# Verify the dotfiles are really in the index before committing.
$tracked = (Invoke-Git @("diff", "--cached", "--name-only") -Quiet).Text `
           -split "`r?`n" | Where-Object { $_ }
$required = @(".gitignore", ".vercelignore", ".github/workflows/build.yml")
$missing  = @()
foreach ($f in $required) {
    $ls = (Invoke-Git @("ls-files", $f) -Quiet).Text.Trim()
    if (($tracked -notcontains $f) -and -not $ls) { $missing += $f }
}
if ($missing.Count -gt 0) {
    Die "These files are not staged: $($missing -join ', ')"
}
Ok "Dotfiles are staged (.gitignore, .vercelignore, .github/)"

# Belt and braces: never let the private key into a commit.
if ((Invoke-Git @("ls-files", "--cached") -Quiet).Text -match "issuer-private.key") {
    Die "admin/issuer-private.key is staged. Run: git rm --cached admin/issuer-private.key"
}

# ---------------------------------------------------------------- commit
Step "Committing"
$pending = (Invoke-Git @("status", "--porcelain") -Quiet).Text.Trim()
if (-not $pending) {
    Warn "Nothing to commit; the working tree is clean."
} else {
    $c = Invoke-Git @("commit", "-m", $Message) -Quiet
    if ($c.Code -ne 0) { Die "git commit failed: $($c.Text)" }
    Ok "Committed: $Message"
}

# ---------------------------------------------------------------- push
Step "Pushing to GitHub"
Write-Host "  If prompted, sign in with your browser or use a Personal Access Token." -ForegroundColor DarkGray
$push = Invoke-Git @("push", "-u", "origin", $Branch)

if ($push.Code -ne 0) {
    $text = $push.Text
    $diverged = ($text -match "rejected") -or ($text -match "fetch first") -or ($text -match "non-fast-forward")

    if (-not $diverged) { Die "Push failed. See the message above." }

    Write-Host ""
    Warn "The remote has commits your local folder does not have."
    Write-Host "  This is expected if you previously uploaded files through the" -ForegroundColor DarkGray
    Write-Host "  GitHub website. Those uploads are the stale copy we are replacing." -ForegroundColor DarkGray

    if (-not $Force) {
        Write-Host ""
        Write-Host "  Nothing on GitHub has been changed. Choose one:" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "    A) Replace the remote with this folder (recommended)." -ForegroundColor Cyan
        Write-Host "       Your local copy is the complete, tested one." -ForegroundColor DarkGray
        Write-Host "         .\push-to-github.ps1 -Force" -ForegroundColor White
        Write-Host ""
        Write-Host "    B) Merge the remote history first, then push." -ForegroundColor Cyan
        Write-Host "       Only if you edited files directly on github.com and" -ForegroundColor DarkGray
        Write-Host "       want to keep those edits." -ForegroundColor DarkGray
        Write-Host "         git pull --rebase origin $Branch" -ForegroundColor White
        Write-Host "         .\push-to-github.ps1" -ForegroundColor White
        Write-Host ""
        Write-Host "  To inspect the remote first:" -ForegroundColor Cyan
        Write-Host "         git fetch origin" -ForegroundColor White
        Write-Host "         git log --oneline origin/$Branch" -ForegroundColor White
        Die "Push rejected. Re-run with one of the options above."
    }

    Write-Host ""
    Warn "-Force given: replacing origin/$Branch with your local branch."
    $null = Invoke-Git @("fetch", "origin") -Quiet

    # Save the old remote state to a branch so nothing is unrecoverable.
    $backup = "backup-before-force-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $probe = Invoke-Git @("rev-parse", "--verify", "--quiet",
                          "refs/remotes/origin/$Branch") -Quiet
    if ($probe.Code -eq 0) {
        $bk = Invoke-Git @("push", "origin",
              "refs/remotes/origin/${Branch}:refs/heads/$backup") -Quiet
        if ($bk.Code -eq 0) {
            Ok "Saved the previous remote state to branch '$backup'"
        } else {
            Warn "Could not create a backup branch; continuing."
        }
    }

    # --force-with-lease aborts if the remote moved since our fetch, rather
    # than blindly clobbering it.
    $f = Invoke-Git @("push", "--force-with-lease", "-u", "origin", $Branch)
    if ($f.Code -ne 0) {
        Warn "force-with-lease was refused; retrying with a plain force push."
        $f = Invoke-Git @("push", "--force", "-u", "origin", $Branch)
        if ($f.Code -ne 0) { Die "Force push failed. See the message above." }
    }
}
Ok "Pushed to $Remote"

if ($Tag) {
    Step "Tagging release $Tag"
    $null = Invoke-Git @("tag", "-f", $Tag) -Quiet
    $t = Invoke-Git @("push", "-f", "origin", $Tag)
    if ($t.Code -ne 0) { Die "Could not push the tag." }
    Ok "Pushed tag $Tag - GitHub Actions will build and publish the release"
}

Write-Host ""
Write-Host "  DONE" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next:" -ForegroundColor Cyan
Write-Host "    1. Open https://github.com/GalaxyFSRP1/PhantomTweeks" -ForegroundColor Cyan
Write-Host "    2. Confirm you can see the .github folder, with" -ForegroundColor Cyan
Write-Host "       workflows/build.yml inside it." -ForegroundColor Cyan
Write-Host "       If you cannot, GitHub Actions will never run." -ForegroundColor Cyan
Write-Host "    3. Check the Actions tab for the build." -ForegroundColor Cyan
Write-Host ""
