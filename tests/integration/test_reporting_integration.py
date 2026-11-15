"""Offline report CLI over real Docker smoke artifacts."""

import json
from pathlib import Path

from test_run_integration import invoke
from test_sandbox_integration import sandbox  # noqa: F401
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.sandbox.runner import SandboxRunner


def test_real_offline_report(sandbox: SandboxRunner, tmp_path: Path) -> None:  # noqa: F811
    suite = invoke(sandbox, tmp_path)
    result = CliRunner().invoke(app, ["report", suite.run_id, "--runs-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "<!doctype html>" in result.stdout and "UNKNOWN" in result.stdout
    assert "Bullseye: 2/2" in result.stdout and "Trace and policy timeline" in result.stdout
    compared = CliRunner().invoke(
        app, ["compare", suite.run_id, suite.run_id, "--runs-root", str(tmp_path)]
    )
    assert compared.exit_code == 0, compared.output
    data = json.loads(compared.stdout)
    assert data["outcomes"]["Bullseye"]["baseline"] == {"numerator": 2, "denominator": 2}
    assert data["quality_delta"] is None
