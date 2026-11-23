"""Verify the scaffold's public command-line behavior."""

import re

import pytest
from typer.testing import CliRunner

from agentforge.cli import app

runner = CliRunner()


@pytest.mark.parametrize("force_color", [False, True])
def test_help(monkeypatch: pytest.MonkeyPatch, force_color: bool) -> None:
    if force_color:
        monkeypatch.setenv("FORCE_COLOR", "1")
    else:
        monkeypatch.delenv("FORCE_COLOR", raising=False)
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Rich can insert SGR color/style codes between the dashes and option name.
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "AgentForge" in output
    assert "--help" in output


def test_unknown_command_is_invalid_input() -> None:
    result = runner.invoke(app, ["not-a-command"])
    assert result.exit_code == 2
    assert "No such command" in result.output
