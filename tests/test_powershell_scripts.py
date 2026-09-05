"""PowerShell scripts must be parseable by Windows PowerShell 5.1.

Two real bugs shipped here, both invisible on Linux:

1. Unix LF line endings broke here-string terminators.
2. A single em dash. Windows PowerShell 5.1 reads a BOM-less file as cp1252,
   where the last byte of UTF-8 "-" (E2 80 94) is 0x94 = a smart quote. That
   opens a string which never closes, and the parser reports the error at the
   *end of the file*, far from the real cause.

The defence is: pure ASCII, CRLF endings, and a UTF-8 BOM.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(ROOT.glob("*.ps1")) + sorted(ROOT.glob("build/*.ps1"))


def test_there_are_powershell_scripts_to_check():
    assert SCRIPTS, "no .ps1 files found"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_uses_crlf_line_endings(script: Path):
    """Windows PowerShell mis-parses LF-only scripts containing here-strings."""
    data = script.read_bytes()
    lf = data.count(b"\n")
    crlf = data.count(b"\r\n")
    assert lf > 0
    assert lf == crlf, (
        f"{script.name} has {lf - crlf} bare LF line ending(s). "
        "Windows PowerShell needs CRLF; see .gitattributes."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_here_strings_are_terminated_at_column_zero(script: Path):
    """A here-string terminator must start at the very beginning of a line."""
    text = script.read_text(encoding="utf-8-sig")
    opens = text.count('@"') + text.count("@'")
    if not opens:
        return
    closes = sum(
        1 for line in text.splitlines()
        if line.startswith('"@') or line.startswith("'@")
    )
    assert closes >= opens, (
        f"{script.name}: {opens} here-string(s) opened but only {closes} "
        "terminator(s) found at column 0. An indented terminator is a parse error."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_has_no_utf8_bom_problems(script: Path):
    """A BOM is tolerated, but the file must decode as UTF-8."""
    script.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_braces_are_balanced_outside_strings_and_comments(script: Path):
    """Cheap structural check for truncation or a botched edit.

    Braces must be counted only in *code*: PowerShell subexpressions like
    "${Branch}" and "$($x)" put braces and parens inside string literals, and
    a naive count reports a false imbalance. This strips comments and the
    contents of quoted strings before counting.
    """
    text = script.read_text(encoding="utf-8-sig")
    out, i, n = [], 0, len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote is None:
            if c == "#":                      # comment to end of line
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if c == "<" and text[i:i + 2] == "<#":   # block comment
                end = text.find("#>", i)
                i = n if end == -1 else end + 2
                continue
            if c in "\"'":
                quote = c
                i += 1
                continue
            out.append(c)
        else:
            if c == "`" and quote == '"':     # backtick escape
                i += 2
                continue
            if c == quote:
                if text[i:i + 2] == quote * 2:  # doubled = literal quote
                    i += 2
                    continue
                quote = None
        i += 1
    code = "".join(out)
    for open_c, close_c in (("{", "}"), ("(", ")")):
        assert code.count(open_c) == code.count(close_c), (
            f"{script.name}: unbalanced {open_c}{close_c} in code "
            f"({code.count(open_c)} vs {code.count(close_c)})"
        )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_parses_with_real_powershell_if_available(script: Path):
    """The authoritative check, when a pwsh binary happens to be present."""
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("PowerShell is not installed in this environment")
    cmd = (
        "$e=$null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script.as_posix()}',[ref]$null,[ref]$e); "
        "if($e -and $e.Count){$e|%{Write-Output $_.Message}; exit 1}"
    )
    r = subprocess.run([pwsh, "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{script.name} parse errors:\n{r.stdout}{r.stderr}"


def test_gitattributes_pins_crlf_for_scripts():
    """Without this, git can rewrite endings on checkout and reintroduce the bug."""
    ga = ROOT / ".gitattributes"
    if not ga.is_file():
        pytest.skip(".gitattributes missing from this checkout "
                    "(use: git add -f .gitattributes)")
    text = ga.read_text(encoding="utf-8")
    assert "*.ps1" in text and "eol=crlf" in text


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_is_pure_ascii(script: Path):
    """Non-ASCII in a .ps1 is a parse hazard under Windows PowerShell 5.1.

    Bytes 0x91-0x94 in cp1252 are smart quotes, which PowerShell treats as
    string delimiters. An em dash in a comment can break the whole file.
    """
    data = script.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    offenders = []
    for lineno, raw in enumerate(data.split(b"\r\n"), 1):
        if any(b > 127 for b in raw):
            offenders.append((lineno, raw.decode("utf-8", "replace")[:80]))
    assert not offenders, (
        f"{script.name} contains non-ASCII characters:\n"
        + "\n".join(f"  line {n}: {t}" for n, t in offenders)
        + "\nReplace them with ASCII equivalents (em dash -> hyphen)."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_has_utf8_bom(script: Path):
    """A BOM stops Windows PowerShell 5.1 falling back to cp1252."""
    assert script.read_bytes().startswith(b"\xef\xbb\xbf"), (
        f"{script.name} has no UTF-8 BOM; PowerShell 5.1 may misdecode it."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_decodes_identically_as_cp1252(script: Path):
    """Simulates exactly how Windows PowerShell 5.1 reads a script.

    If the cp1252 and UTF-8 readings differ, the file means something
    different on Windows than it does here, which is how the em-dash bug
    escaped every check that ran on Linux.
    """
    data = script.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        as_cp1252 = data.decode("cp1252")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{script.name} is not decodable as cp1252: {exc}")
    assert as_cp1252 == data.decode("utf-8"), (
        f"{script.name} reads differently under cp1252 than UTF-8."
    )
