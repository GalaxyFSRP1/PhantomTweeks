<#
.SYNOPSIS
    Builds Phantom Tweeks into distributable Windows binaries.

.DESCRIPTION
    Produces:
        /dist/PhantomTweeks.exe            main application
        /dist/PhantomTweeks-Portable.exe   single-file portable build
        /dist/PhantomTweeks-Setup.exe      installer (requires Inno Setup)

    Run from the repository root:
        .\build.ps1
        .\build.ps1 -SkipTests
        .\build.ps1 -Sign -CertThumbprint <thumbprint>

.NOTES
    Distribute signed binaries only. Unsigned builds trigger SmartScreen and,
    more importantly, give your users no way to verify what they are running.
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$SkipMsi,
    [switch]$Sign,
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
# Set if the optional MSI step fails; reported in the summary so a missing
# .msi is never mistaken for a complete release.
$script:MsiFailed = $false
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\_work"
$AppName = "Phantom Tweeks"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "`n  [FAIL] $msg" -ForegroundColor Red; exit 1 }

# Read the version from branding.py, which is the single source of truth.
# It was hard-coded here and silently went stale: a v0.1.4 release shipped a
# file called PhantomTweeks-0.1.2.msi. Never duplicate the version.
$brandingFile = Join-Path $Root "src\phantom_tweeks\branding.py"
if (-not (Test-Path $brandingFile)) { Fail "Cannot find branding.py to read the version." }
$versionMatch = Select-String -Path $brandingFile -Pattern 'VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) { Fail "branding.py does not declare VERSION." }
$Version = $versionMatch.Matches[0].Groups[1].Value


Write-Host ""
Write-Host "  PHANTOM TWEEKS BUILD" -ForegroundColor Cyan
Write-Host "  $AppName $Version" -ForegroundColor Cyan
Write-Host "  Optimize Smarter. Game Better." -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- environment
Write-Step "Checking environment"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Fail "Python 3.10+ is required and was not found on PATH." }
$pyVer = (& python -c "import sys;print('.'.join(map(str,sys.version_info[:2])))").Trim()
if ([version]$pyVer -lt [version]"3.10") { Fail "Python $pyVer found; 3.10 or newer is required." }
Write-Ok "Python $pyVer"

if ($Clean) {
    Write-Step "Cleaning"
    foreach ($p in @($Dist, $Work, (Join-Path $Root "build\__pycache__"))) {
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
    Write-Ok "Removed previous build output"
}

# ---------------------------------------------------------------- venv + deps
Write-Step "Preparing build environment"
$Venv = Join-Path $Root ".venv-build"
if (-not (Test-Path $Venv)) { & python -m venv $Venv }
$VPy = Join-Path $Venv "Scripts\python.exe"
& $VPy -m pip install --upgrade pip --quiet
& $VPy -m pip install -r (Join-Path $Root "requirements-dev.txt") --quiet
if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed." }
Write-Ok "Dependencies installed"

# ---------------------------------------------------------------- tests
if (-not $SkipTests) {
    Write-Step "Running test suite"
    # Deselect repo-hygiene checks: they lint CI/repository config, not the
    # product. A stale or missing .github/workflows file must never stop a
    # release build of a working binary.
    & $VPy -m pytest (Join-Path $Root "tests") -q -m "not repo_hygiene"
    if ($LASTEXITCODE -ne 0) {
        Fail "Tests failed. Refusing to build a release from a failing tree."
    }
    Write-Ok "All tests passed"
} else {
    Write-Warn2 "Tests skipped (-SkipTests). Do not ship this build."
}

# ---------------------------------------------------------------- icon
Write-Step "Verifying assets"
$Icon = Join-Path $Root "assets\phantom.ico"
if (-not (Test-Path $Icon)) { Fail "assets\phantom.ico is missing." }
Write-Ok "Application icon present"

$Launcher = Join-Path $Root "build\phantom_launcher.py"
if (-not (Test-Path $Launcher)) {
    Fail "build\phantom_launcher.py is missing. The frozen build needs it: " +
         "using the package __main__.py as the entry script breaks relative imports."
}
Write-Ok "Frozen entry point present"

# The issuer private key must never end up inside a shipped binary.
$Secret = Join-Path $Root "admin\issuer-private.key"
if (Test-Path $Secret) {
    Write-Warn2 "admin\issuer-private.key exists locally. It is NOT bundled"
    Write-Warn2 "(the spec only includes assets/ and docs/), but never commit it."
}

# ---------------------------------------------------------------- binaries
$env:PHANTOM_BUILD_ROOT = $Root
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

Write-Step "Building PhantomTweeks.exe"
$env:PHANTOM_PORTABLE = "0"
& $VPy -m PyInstaller (Join-Path $Root "build\PhantomTweeks.spec") `
    --distpath $Dist --workpath (Join-Path $Work "installed") --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed for the main build." }
if (-not (Test-Path (Join-Path $Dist "PhantomTweeks.exe"))) {
    Fail "PyInstaller reported success but dist\PhantomTweeks.exe is missing."
}
Write-Ok "dist\PhantomTweeks.exe"

Write-Step "Building PhantomTweeks-Portable.exe"
$env:PHANTOM_PORTABLE = "1"
# NOTE: do NOT pass --onefile/--onedir here. The .spec already emits a
# single-file EXE (binaries+datas go straight into EXE(), no COLLECT), and
# PyInstaller rejects makespec flags when a .spec is supplied.
# The portable variant differs via PHANTOM_PORTABLE, read by the spec.
& $VPy -m PyInstaller (Join-Path $Root "build\PhantomTweeks.spec") `
    --distpath $Dist --workpath (Join-Path $Work "portable") --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed for the portable build." }
if (-not (Test-Path (Join-Path $Dist "PhantomTweeks-Portable.exe"))) {
    Fail "PyInstaller reported success but dist\PhantomTweeks-Portable.exe is missing."
}
Write-Ok "dist\PhantomTweeks-Portable.exe"

# ---------------------------------------------------------------- signing
function Invoke-Sign([string]$Path) {
    if (-not $Sign) { return }
    if (-not $CertThumbprint) { Fail "-Sign requires -CertThumbprint." }
    $st = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $st) { Fail "signtool.exe not found. Install the Windows SDK." }
    & signtool.exe sign /sha1 $CertThumbprint /fd SHA256 /td SHA256 `
        /tr $TimestampUrl /d "$AppName" $Path
    if ($LASTEXITCODE -ne 0) { Fail "Signing failed for $Path" }
    Write-Ok "Signed $(Split-Path $Path -Leaf)"
}

if ($Sign) {
    Write-Step "Code signing"
    Invoke-Sign (Join-Path $Dist "PhantomTweeks.exe")
    Invoke-Sign (Join-Path $Dist "PhantomTweeks-Portable.exe")
} else {
    Write-Warn2 "Binaries are UNSIGNED. Do not distribute unsigned builds publicly:"
    Write-Warn2 "users cannot verify them and SmartScreen will block the download."
}

# ---------------------------------------------------------------- installer
if (-not $SkipInstaller) {
    Write-Step "Building installer"
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $guess = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $guess) { $iscc = $guess } else { $iscc = $null }
    }
    if ($iscc) {
        & $iscc (Join-Path $Root "build\installer.iss") /Q
        if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed." }
        Invoke-Sign (Join-Path $Dist "PhantomTweeks-Setup.exe")
        Write-Ok "dist\PhantomTweeks-Setup.exe"
    } else {
        Write-Warn2 "Inno Setup 6 not found; skipping installer."
        Write-Warn2 "Install from https://jrsoftware.org/isdl.php to enable it."
    }
}

# ---------------------------------------------------------------- MSI (WiX)
if (-not $SkipMsi) {
    Write-Step "Building MSI package"

    # WiX needs an RTF licence; generate one from the plain-text EULA so the
    # two can never drift apart.
    $eula = Join-Path $Root "docs\EULA.txt"
    $rtf  = Join-Path $Work "EULA.rtf"
    New-Item -ItemType Directory -Force -Path $Work | Out-Null
    $body = (Get-Content $eula -Raw) -replace '\\', '\\\\' `
                                     -replace '\{', '\{' -replace '\}', '\}'
    $body = $body -replace "`r`n", "\par`r`n"
    "{\rtf1\ansi\deff0{\fonttbl{\f0 Segoe UI;}}\fs18 $body }" |
        Set-Content -Path $rtf -Encoding ASCII
    Write-Ok "Generated EULA.rtf for the MSI wizard"

    $wix = Get-Command wix.exe -ErrorAction SilentlyContinue
    if (-not $wix) {
        Write-Warn2 "WiX Toolset not found; skipping the .msi."
        Write-Warn2 "Install it with:"
        Write-Warn2 "  dotnet tool install --global wix --version 5.0.2"
        Write-Warn2 "(v6+ requires paying the Open Source Maintenance Fee;"
        Write-Warn2 " v5.0.2 is the last release without that requirement.)"
        Write-Warn2 "The .exe installer was still produced."
    } else {
        # The wizard UI lives in a separate WiX v4 extension. The previous
        # version discarded the result of "extension add", so a failed install
        # only surfaced later as "the extension could not be found".
        $uiExt = $true
        # Pin the extension to the same version as the pinned toolset.
        $addLog = & wix.exe extension add -g WixToolset.UI.wixext/5.0.2 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Fall back to an unversioned add for a locally installed v5.
            $addLog = & wix.exe extension add -g WixToolset.UI.wixext 2>&1
        }
        if ($LASTEXITCODE -ne 0) {
            $uiExt = $false
            Write-Warn2 "Could not install WixToolset.UI.wixext:"
            Write-Warn2 (($addLog | Out-String).Trim())
        } else {
            $have = (& wix.exe extension list -g 2>&1 | Out-String)
            if ($have -notmatch "WixToolset.UI.wixext") { $uiExt = $false }
        }

        if ($uiExt) {
            Write-Ok "WiX UI extension available"
        } else {
            Write-Warn2 "Building the MSI without the wizard UI. It still"
            Write-Warn2 "installs correctly via msiexec, which is what managed"
            Write-Warn2 "deployment uses. The .exe installer is unaffected."
        }

        $msiOut = Join-Path $Dist "PhantomTweeks-$Version.msi"
        $wixArgs = @(
            "build", (Join-Path $Root "build\PhantomTweeks.wxs"),
            "-arch", "x64",
            "-d", "ProductVersion=$Version",
            "-d", "DistDir=$Dist",
            "-d", ("AssetsDir=" + (Join-Path $Root "assets")),
            "-d", ("DocsDir=" + (Join-Path $Root "docs")),
            "-d", "LicenseRtf=$rtf",
            "-o", $msiOut
        )
        if ($uiExt) {
            $wixArgs += @("-ext", "WixToolset.UI.wixext", "-d", "IncludeUI=1")
        }

        $wixLog = (& wix.exe @wixArgs 2>&1 | Tee-Object -Variable wixOut | Out-String)
        Write-Host $wixLog.TrimEnd()
        if ($wixLog -match "WIX7015" -or $wixLog -match "Maintenance Fee") {
            Write-Warn2 "This WiX version requires accepting the Open Source"
            Write-Warn2 "Maintenance Fee EULA (WiX v6 and later)."
            Write-Warn2 "Either install the last fee-free release:"
            Write-Warn2 "  dotnet tool uninstall --global wix"
            Write-Warn2 "  dotnet tool install --global wix --version 5.0.2"
            Write-Warn2 "or, if you qualify and agree, run:  wix eula accept wix7"
            Write-Warn2 "See https://wixtoolset.org/osmf/ for the terms."
        }
        if ($LASTEXITCODE -ne 0) {
            # An optional packaging format must never sink a good build; the
            # binaries and the .exe installer are already on disk.
            Write-Warn2 "WiX failed to build the MSI (see the output above)."
            Write-Warn2 "The .exe installer and portable build are unaffected."
            $script:MsiFailed = $true
        }
        elseif (-not (Test-Path $msiOut)) {
            Write-Warn2 "WiX reported success but $msiOut is missing."
            $script:MsiFailed = $true
        }
        else {
            Invoke-Sign $msiOut
            Write-Ok "dist\PhantomTweeks-$Version.msi"
        }
    }
}

# ---------------------------------------------------------------- checksums
Write-Step "Generating SHA-256 checksums"
$sumFile = Join-Path $Dist "SHA256SUMS.txt"
if (Test-Path $sumFile) { Remove-Item $sumFile -Force }
Get-ChildItem $Dist -Include *.exe, *.msi -Recurse | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$h  $($_.Name)" | Add-Content $sumFile
    Write-Host "  $($_.Name)" -ForegroundColor Gray
    Write-Host "    $h" -ForegroundColor DarkGray
}
Write-Ok "dist\SHA256SUMS.txt"

Write-Host ""
Write-Host "  BUILD COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output in: $Dist" -ForegroundColor Cyan
Get-ChildItem $Dist -Include *.exe, *.msi, SHA256SUMS.txt -Recurse |
    Sort-Object Name | ForEach-Object {
        $mb = [math]::Round($_.Length / 1MB, 1)
        Write-Host ("    {0,-34} {1,6} MB" -f $_.Name, $mb) -ForegroundColor Gray
    }
Write-Host ""
if ($script:MsiFailed) {
    Write-Host "  The .msi was NOT produced. See the WiX errors above." -ForegroundColor Yellow
    Write-Host "  Everything else built normally. The .exe installer is what" -ForegroundColor Yellow
    Write-Host "  end users need; the .msi only matters for managed deployment" -ForegroundColor Yellow
    Write-Host "  via Group Policy or Intune." -ForegroundColor Yellow
    Write-Host ""
}
Write-Host "  Publish the SHA-256 values on the download page so users can" -ForegroundColor Cyan
Write-Host "  verify what they downloaded. Sign your binaries before public" -ForegroundColor Cyan
Write-Host "  distribution." -ForegroundColor Cyan
Write-Host ""
