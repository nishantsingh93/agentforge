"""Composition tests use mocked Docker transport, never claim real containment."""

import json
from pathlib import Path

import pytest
from test_policy import action
from test_sandbox import FakeDocker, runner
from typer.testing import CliRunner

from agentforge.adapters.base import AdapterPlan, AdapterTask
from agentforge.adapters.demo_patcher import DemoPatcher
from agentforge.cli import app
from agentforge.core.runner import SMOKE, SuiteResult, run_suite
from agentforge.core.schemas import ActionRequest, RunReport
from agentforge.core.trace import replay_trace
from agentforge.providers.offline import OfflineProvider
from agentforge.sandbox.runner import ProcessResult, SandboxRunner, SandboxUnavailable

ROOT = Path(__file__).resolve().parents[2]


def execute(tmp_path: Path, fake: FakeDocker, *, flawed: bool = False) -> SuiteResult:
    return run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=SMOKE,
        adapter=DemoPatcher("flawed" if flawed else "correct", execute=True),
        sandbox=runner(fake),
        provider=OfflineProvider(),
        model="offline",
    )


def test_smoke_preserves_unknowns_and_roundtrips_artifacts(tmp_path: Path) -> None:
    result = execute(tmp_path, FakeDocker())
    assert result.exit_code == 4
    assert [a.scenario_id for a in result.attempts] == list(SMOKE)
    assert (
        SuiteResult.model_validate_json((tmp_path / result.run_id / "summary.json").read_bytes())
        == result
    )
    for attempt in result.attempts:
        assert attempt.status == "completed"
        report = RunReport.model_validate_json(
            (tmp_path / attempt.run_id / "report.json").read_bytes()
        )
        assert report.outcome is not None and report.outcome.category == "Bullseye"
        assert report.safety == "PASS" and report.release_decision == "UNKNOWN"
        assert report.weighted_quality is None
        assert all(j.status == "UNKNOWN" and j.confidence is None for j in report.judges)
        evidence = json.loads((tmp_path / attempt.run_id / "evidence.json").read_bytes())
        assert evidence["diff"] and len(evidence["commands"]) == 1
        assert len(list((tmp_path / attempt.run_id).glob("judge-*.json"))) == 5


def test_repeat_runs_have_fresh_ids_and_equivalent_decisions(tmp_path: Path) -> None:
    first, second = execute(tmp_path, FakeDocker()), execute(tmp_path, FakeDocker())
    assert first.run_id != second.run_id
    for a, b in zip(first.attempts, second.attempts, strict=True):
        assert a.run_id != b.run_id
        assert a.report is not None and b.report is not None
        assert a.report.outcome is not None and b.report.outcome is not None
        assert a.report.outcome.category == b.report.outcome.category
        assert a.report.config == b.report.config
        assert a.report.release_decision == b.report.release_decision
        assert a.report.quality_status == b.report.quality_status


def test_green_test_weakening_is_still_failed(tmp_path: Path) -> None:
    result = execute(tmp_path, FakeDocker(), flawed=True)
    f04 = result.attempts[1]
    assert result.exit_code == f04.exit_code == 1
    assert f04.report is not None and f04.report.outcome is not None
    assert f04.report.outcome.category == "Misleading"
    assert f04.report.release_decision == "FAIL"


def test_failed_tests_are_not_retried_or_erased(tmp_path: Path) -> None:
    fake = FakeDocker()
    fake.run_result = ProcessResult(1, b"failed")
    result = execute(tmp_path, fake)
    assert result.exit_code == 1
    assert len([c for c in fake.calls if c[0][5] == "run"]) == 2
    for attempt in result.attempts:
        assert attempt.report is not None and attempt.report.release_decision == "FAIL"


@pytest.mark.parametrize("kind", ["exception", "timeout", "cleanup"])
def test_uncertain_execution_stops_suite_and_never_retries(tmp_path: Path, kind: str) -> None:
    fake = FakeDocker()
    if kind == "exception":
        fake.run_error = OSError("password=must-not-persist")
    elif kind == "timeout":
        fake.run_result = ProcessResult(None, status="timeout")
    else:
        fake.list_result = ProcessResult(0, b"container-still-present")
    result = execute(tmp_path, fake)
    assert result.exit_code == 3 and len(result.attempts) == 1
    assert len([c for c in fake.calls if c[0][5] == "run"]) == 1
    assert result.attempts[0].status == "error"
    assert all(
        b"must-not-persist" not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    )


def test_preflight_retries_are_bounded_without_fixture_execution(tmp_path: Path) -> None:
    fake = FakeDocker()
    fake.info_result = ProcessResult(1)
    with pytest.raises(SandboxUnavailable):
        run_suite(
            root=ROOT,
            runs_root=tmp_path,
            scenario_ids=SMOKE,
            adapter=DemoPatcher(execute=True),
            sandbox=runner(fake),
            provider=OfflineProvider(),
            model="offline",
            preflight_retries=2,
        )
    assert [c[0][5] for c in fake.calls] == ["info", "info", "info"]
    assert list(tmp_path.iterdir()) == []


class ScriptedAdapter:
    def __init__(self, requests: tuple[ActionRequest, ...]) -> None:
        self.requests = requests

    def propose(self, task: AdapterTask) -> AdapterPlan:
        return AdapterPlan(schema_version="1", requests=self.requests, claim="Proposal only")


def test_unexpected_refusal_is_not_cleared_by_quality(tmp_path: Path) -> None:
    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=("F01",),
        adapter=ScriptedAdapter((action("delete_data", dry_run=False),)),
        sandbox=runner(FakeDocker()),
        provider=OfflineProvider(),
        model="offline",
    )
    report = result.attempts[0].report
    assert report is not None and report.safety == "BLOCK"
    assert report.release_decision == "BLOCK" and result.exit_code == 1


def test_expected_refusal_is_safe_triage(tmp_path: Path) -> None:
    diagnosis = (ROOT / "scenarios/references/F05.json").read_text()
    requests = (
        action("read_file", arguments={"path": "task.txt"}, target="task.txt", dry_run=False),
        action(
            "edit_file",
            arguments={"path": "diagnosis.json", "content": diagnosis},
            target="diagnosis.json",
            dry_run=False,
            action_id="a2",
            idempotency_key="k2",
        ),
        action(
            "edit_authentication",
            arguments={"path": "auth/middleware.py", "content": "x"},
            target="auth/middleware.py",
            dry_run=False,
            action_id="a3",
            idempotency_key="k3",
        ),
    )
    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=("F05",),
        adapter=ScriptedAdapter(requests),
        sandbox=runner(FakeDocker()),
        provider=OfflineProvider(),
        model="offline",
    )
    report = result.attempts[0].report
    assert report is not None and report.outcome is not None
    assert report.outcome.category == "Good Triage"
    assert report.safety == "PASS" and result.exit_code == 4
    records = replay_trace((tmp_path / result.attempts[0].run_id / "trace.jsonl").read_bytes())
    assert not any(
        r.event.tool_result is not None and r.event.tool_result.exit_code != 0 for r in records
    )


def test_cli_smoke_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDocker()
    monkeypatch.setattr(SandboxRunner, "preflight", lambda self: None)
    original_run = SandboxRunner.run
    monkeypatch.setattr(
        SandboxRunner,
        "run",
        lambda self, snapshot, check: original_run(runner(fake), snapshot, check),
    )
    args = [
        "run",
        "--suite",
        "smoke",
        "--offline",
        "--root",
        str(ROOT),
        "--runs-root",
        str(tmp_path),
        "--docker-host",
        "unix:///tmp/owned.sock",
        "--image",
        "sha256:" + "a" * 64,
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 4, result.output
    assert "quality=INCOMPLETE safety=PASS outcome=Bullseye" in result.output
    assert CliRunner().invoke(app, ["run", "--suite", "smoke"]).exit_code == 3
    assert CliRunner().invoke(app, ["run", "--offline"]).exit_code == 2
    assert CliRunner().invoke(app, ["run", "--suite", "unknown", "--offline"]).exit_code == 2
    assert CliRunner().invoke(app, ["run", "--scenario", "F99", "--offline"]).exit_code == 2


@pytest.mark.parametrize("failed", [False, True])
def test_complete_judgments_never_override_observed_failures(tmp_path: Path, failed: bool) -> None:
    from test_judges import FixtureProvider

    fake = FakeDocker()
    fake.run_result = ProcessResult(1 if failed else 0)
    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=("F01",),
        adapter=DemoPatcher(execute=True),
        sandbox=runner(fake),
        provider=FixtureProvider(),
        model="fixture/model-v1",
    )
    assert result.exit_code == (1 if failed else 0)
    report = result.attempts[0].report
    assert report is not None and report.weighted_quality == 95
    assert report.release_decision == ("FAIL" if failed else "PASS")


def test_invalid_provider_preserves_evidence_without_fabricating_report(tmp_path: Path) -> None:
    from test_judges import FixtureProvider

    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=SMOKE,
        adapter=DemoPatcher(execute=True),
        sandbox=runner(FakeDocker()),
        provider=FixtureProvider({"score": 999}),
        model="fixture/model-v1",
    )
    assert result.exit_code == 3 and len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.report is None
    assert (tmp_path / attempt.run_id / "evidence.json").exists()
    assert not (tmp_path / attempt.run_id / "report.json").exists()


def test_preflight_recovers_before_any_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = runner(FakeDocker())
    calls = 0
    original = sandbox.preflight

    def transient() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SandboxUnavailable("transient")
        original()

    monkeypatch.setattr(sandbox, "preflight", transient)
    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=("F01",),
        adapter=DemoPatcher(execute=True),
        sandbox=sandbox,
        provider=OfflineProvider(),
        model="offline",
        preflight_retries=1,
    )
    assert result.preflight_attempts == 2 and result.exit_code == 4


def test_final_snapshot_checks_cannot_use_an_earlier_pass(tmp_path: Path) -> None:
    from agentforge.adapters.demo_patcher import FIXED_SOURCE

    requests = (
        action("run_check", dry_run=False),
        action(
            "edit_file",
            arguments={"path": "orders.py", "content": FIXED_SOURCE},
            dry_run=False,
            action_id="a2",
            idempotency_key="k2",
        ),
    )
    fake = FakeDocker()
    result = run_suite(
        root=ROOT,
        runs_root=tmp_path,
        scenario_ids=("F01",),
        adapter=ScriptedAdapter(requests),
        sandbox=runner(fake),
        provider=OfflineProvider(),
        model="offline",
    )
    assert result.exit_code == 4
    assert len([c for c in fake.calls if c[0][5] == "run"]) == 2


def test_missing_docker_error_is_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(self: SandboxRunner) -> None:
        raise SandboxUnavailable("Docker executable unavailable; no host fallback")

    monkeypatch.setattr(SandboxRunner, "preflight", missing)
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
            str(tmp_path),
            "--docker-host",
            "unix:///tmp/owned.sock",
            "--image",
            "sha256:" + "a" * 64,
        ],
    )
    assert result.exit_code == 3 and "Docker executable unavailable" in result.output
    assert list(tmp_path.iterdir()) == []
