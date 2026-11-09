"""Tests for CLI --version option across commands."""

from __future__ import annotations

import sys

import pytest

from freefox import __version__
from freefox.dashboard import main as dashboard_main
from freefox.service import main as service_main
from freefox.status import main as status_main


@pytest.mark.parametrize(
    "main_func",
    [service_main, dashboard_main, status_main],
)
def test_cli_version_flag(main_func, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["prog", "--version"])
    with pytest.raises(SystemExit) as exc_info:
        main_func()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    output = captured.out or captured.err
    assert output.strip() == f"freefox {__version__}"
