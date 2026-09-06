"""CLI surface and confirmation requirements."""
import pytest

from phantom_tweeks.cli.main import build_parser

EXPECTED = {"scan", "optimize", "benchmark", "network-test", "restore",
            "hardware", "version", "shield", "score", "bottleneck", "games",
            "background", "startup", "drivers", "storage", "health",
            "profiles", "snapshot", "premium", "expert", "config", "gui",
            "network-history", "compare"}


def test_all_documented_commands_exist():
    parser = build_parser()
    sub = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    assert EXPECTED.issubset(set(sub.choices))


@pytest.mark.parametrize("cmd", ["optimize", "restore", "config"])
def test_mutating_commands_have_confirmation_flag(cmd):
    parser = build_parser()
    sub = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    opts = {o for act in sub.choices[cmd]._actions for o in act.option_strings}
    assert "--yes" in opts, f"{cmd} must support explicit confirmation"


def test_read_only_commands_parse():
    parser = build_parser()
    for cmd in ("version", "hardware", "shield", "scan", "score", "health"):
        assert parser.parse_args([cmd]).command == cmd


def test_restore_all_flag_exists():
    args = build_parser().parse_args(["restore", "--all", "--yes"])
    assert args.all and args.yes
