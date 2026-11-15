"""Verify the scaffold's public command-line behavior."""

from typer.testing import CliRunner

from agentforge.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AgentForge" in result.output
    assert "--help" in result.output


def test_unknown_command_is_invalid_input() -> None:
    result = runner.invoke(app, ["not-a-command"])
    assert result.exit_code == 2
    assert "No such command" in result.output
