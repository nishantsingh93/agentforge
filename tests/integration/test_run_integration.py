"""Real CLI smoke, repeatability and deliberately flawed demo acceptance checks."""

import json
from pathlib import Path

from test_sandbox_integration import sandbox  # noqa: F401
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.core.runner import SuiteResult
from agentforge.sandbox.runner import SandboxRunner

ROOT = Path(__file__).resolve().parents[2]


def invoke(engine: SandboxRunner, destination: Path, flawed: bool = False) -> SuiteResult:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--suite",
            "smoke",
            "--offline",
            "--root",
            str(ROOT),
            "--runs-root",
            str(destination),
            "--docker-host",
            engine.config.docker_host,
            "--image",
            engine.config.image,
            "--agent",
            "demo-patcher-flawed" if flawed else "demo-patcher",
        ],
    )
    assert result.exit_code == (1 if flawed else 4), result.output
    summaries = list(destination.glob("suite-*/summary.json"))
    assert len(summaries) == 1
    return SuiteResult.model_validate_json(summaries[0].read_bytes())


def test_real_cli_smoke(sandbox: SandboxRunner, tmp_path: Path) -> None:  # noqa: F811
    result = invoke(sandbox, tmp_path)
    assert len(result.attempts) == 2
    for attempt in result.attempts:
        report = attempt.report
        assert report is not None and report.outcome is not None
        assert report.outcome.category == "Bullseye"
        assert report.safety == "PASS" and report.release_decision == "UNKNOWN"
        bundle = json.loads((tmp_path / attempt.run_id / "evidence.json").read_bytes())
        assert len(bundle["commands"]) == 1
        assert bundle["commands"][0]["exit_code"] == 0
        assert bundle["commands"][0]["status"] == "completed"


def test_real_cli_repeatability(sandbox: SandboxRunner, tmp_path: Path) -> None:  # noqa: F811
    first, second = invoke(sandbox, tmp_path / "first"), invoke(sandbox, tmp_path / "second")
    assert first.run_id != second.run_id
    for a, b in zip(first.attempts, second.attempts, strict=True):
        assert a.report is not None and b.report is not None
        assert a.report.outcome is not None and b.report.outcome is not None
        assert a.run_id != b.run_id
        assert a.report.config == b.report.config
        assert a.report.outcome.category == b.report.outcome.category == "Bullseye"
        assert a.report.release_decision == b.report.release_decision == "UNKNOWN"


def test_real_cli_flawed_demo(sandbox: SandboxRunner, tmp_path: Path) -> None:  # noqa: F811
    result = invoke(sandbox, tmp_path, flawed=True)
    assert len(result.attempts) == 2
    for attempt in result.attempts:
        assert attempt.report is not None and attempt.report.release_decision == "FAIL"
    f04 = result.attempts[1]
    assert f04.report is not None and f04.report.outcome is not None
    assert f04.report.outcome.category == "Misleading"
    bundle = json.loads((tmp_path / f04.run_id / "evidence.json").read_bytes())
    assert bundle["commands"][0]["exit_code"] == 0  # Oracle catches test weakening.
