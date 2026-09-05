# Building & Distributing Phantom Tweeks

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10/11 x64 | Required to build shippable binaries |
| Python 3.10+ | On PATH as `python` |
| Inno Setup 6 | Optional, for the installer — https://jrsoftware.org/isdl.php |
| Windows SDK | Optional, provides `signtool.exe` for code signing |
| Code-signing certificate | Strongly recommended before public distribution |

## Running from source first

Before building, confirm the app runs:

```powershell
pip install -r requirements.txt
python run.py version
```

Use `run.py` rather than `python -m phantom_tweeks` — the `src/` layout means the module form
requires `pip install -e .` first.

## Build

```powershell
.\build.ps1                                    # standard build
.\build.ps1 -Clean                             # wipe previous output first
.\build.ps1 -SkipTests                         # not for release builds
.\build.ps1 -SkipInstaller                     # binaries only
.\build.ps1 -Sign -CertThumbprint <thumbprint> # signed release
```

`build.ps1` will:

1. Verify Python 3.10+
2. Create `.venv-build` and install `requirements-dev.txt`
3. **Run the test suite and refuse to build if it fails**
4. Verify the application icon exists
5. Build `PhantomTweeks.exe` and `PhantomTweeks-Portable.exe` via PyInstaller
6. Optionally sign both with SHA-256 and an RFC 3161 timestamp
7. Build `PhantomTweeks-Setup.exe` via Inno Setup and sign it
8. Write `dist\SHA256SUMS.txt`

## Output

```
dist/
├── PhantomTweeks.exe
├── PhantomTweeks-Portable.exe
├── PhantomTweeks-Setup.exe
└── SHA256SUMS.txt
```

## Version information

Both the icon (`assets/phantom.ico`) and Windows version metadata (`version_info.txt`) are
embedded. Update `version_info.txt`, `pyproject.toml` and `src/phantom_tweeks/branding.py`
together when bumping the version — `branding.VERSION` is the runtime source of truth.

## Distribution checklist

- [ ] Tests pass (`python -m pytest tests -q`)
- [ ] Version bumped in `branding.py`, `pyproject.toml`, `version_info.txt`, `installer.iss`
- [ ] Binaries **Authenticode-signed** with a timestamp
- [ ] `SHA256SUMS.txt` published on the download page
- [ ] Release notes updated on `website/download.html`
- [ ] Installer tested on a clean Windows 10 **and** Windows 11 VM
- [ ] RESTORE EVERYTHING verified end-to-end on a test machine
- [ ] Uninstall verified to leave backups intact

> **Never distribute unsigned or tampered binaries.** An unsigned executable that edits the
> registry is indistinguishable from malware, both to SmartScreen and to a careful user.

## Update server

`core/updates.py` expects a manifest at `UPDATE_MANIFEST_URL`:

```json
{
  "version": "1.0.1",
  "url": "https://.../PhantomTweeks-Setup.exe",
  "sha256": "<64 hex characters>",
  "notes": "Release notes text",
  "mandatory": false
}
```

Both URLs must be HTTPS or the client refuses them. The payload must pass SHA-256 **and**
Authenticode verification before being staged; the updater never executes anything.

## Website

`website/` is static HTML with no build step and no external dependencies. Deploy the folder to
any static host. After a release, update the download links, SHA-256 table and release notes on
`download.html`.

## GUI tests and Tk availability

The rendering tests in `tests/test_gui_render.py` construct a real window.
They **skip themselves** when Tk cannot render, rather than failing:

* headless Linux with no `DISPLAY`;
* a Python whose Tcl data files are missing. GitHub's hosted Windows runners
  have shipped in this state, producing
  `TclError: Can't find a usable init.tcl`.

That is a broken *environment*, not a product defect, and it must never block
a release build — it did once, and the release stalled for no good reason.

The probe does more than call `Tk()`: it also creates a themed widget, because
a damaged Tcl install can survive construction and only fail later.

CI runs a `TK_OK` probe and emits a `::warning::` when Tk is unusable, so a
run where the GUI was never exercised is visible rather than silent. If you
see that warning, the packaged GUI is **not** covered by that run.

To run the GUI tests locally on Linux you need an X server:

```bash
sudo apt-get install xvfb
xvfb-run -a python -m pytest tests/test_gui_render.py -q
```
