"""AF-009 synthetic runtime acceptance; fake Docker is not containment evidence."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_policy import action, context
from test_sandbox import FakeDocker, runner, snapshot

from agentforge.core.evidence import EvidenceCollector
from agentforge.core.schemas import ActionRequest
from agentforge.core.trace import replay_trace
from agentforge.guardrails.approvals import ApprovalRegistry
from agentforge.guardrails.executor import FixtureExecutor
from agentforge.guardrails.gateway import Gateway
from agentforge.guardrails.policy import POLICY_VERSION
from agentforge.runtime.checks import assess_check, run_checks
from agentforge.runtime.rollout import (
    Health,
    RolloutResult,
    RolloutSimulator,
    Simulation,
    Thresholds,
)
from agentforge.sandbox.runner import ProcessResult


def health(sample_phase: str, **changes: Any) -> Health:
    return Health.model_validate(
        {
            "phase": sample_phase,
            "error_rate": 0.001,
            "p95_ms": 100.0,
            "availability": 1.0,
            "business_success": 1.0,
            "window_seconds": 60.0,
            "age_seconds": 0.0,
            **changes,
        }
    )


def config(**changes: Any) -> Simulation:
    return Simulation.model_validate(
        {
            "schema_version": "1",
            "service": "orders",
            "baseline_version": "v1",
            "candidate_version": "v2",
            "thresholds": Thresholds(),
            "baseline": health("baseline"),
            "canary": health("canary"),
            "rollback": health("rollback"),
            **changes,
        }
    )


def test_healthy_canary_and_single_use_isolation() -> None:
    first, second = RolloutSimulator(config()), RolloutSimulator(config())
    result = first.execute("orders")
    assert result.status == "expanded"
    assert [s.phase for s in result.steps] == ["baseline", "canary", "expanded"]
    assert first.state.version == "v2" and second.state.version == "v1"
    assert RolloutResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValueError, match="used"):
        first.execute("orders")
    assert first.state.version == "v2"


@pytest.mark.parametrize(
    "metric,value",
    [
        ("error_rate", 0.02),
        ("p95_ms", 501.0),
        ("availability", 0.98),
        ("business_success", 0.97),
        ("age_seconds", 6.0),
        ("window_seconds", 59.0),
        ("phase", "baseline"),
    ],
)
def test_unhealthy_canary_stops_and_verifies_actual_rollback(metric: str, value: Any) -> None:
    simulator = RolloutSimulator(config(canary=health("canary", **{metric: value})))
    before = simulator.state
    result = simulator.execute("orders")
    assert result.status == "recovered"
    assert [s.phase for s in result.steps] == ["baseline", "canary", "stopped", "rollback"]
    assert simulator.state == before == result.steps[-1].state
    assert all(s.phase != "expanded" for s in result.steps)


@pytest.mark.parametrize("fault", ["failed", "spoofed-success"])
def test_failed_rollback_escalates_despite_claim(fault: str) -> None:
    simulator = RolloutSimulator(config(canary=None, rollback_fault=fault))
    result = simulator.execute("orders")
    assert result.status == "escalated" and result.reason == "rollback-unverified"
    assert simulator.state != result.steps[0].state
    assert result.steps[-1].claimed_success == (fault == "spoofed-success")
    with pytest.raises(ValueError):
        simulator.execute("orders")


@pytest.mark.parametrize("phase", ["baseline", "canary", "rollback"])
@pytest.mark.parametrize("fault", ["missing", "stale", "short", "unhealthy"])
def test_missing_health_blocks_continuation(phase: str, fault: str) -> None:
    sample = (
        None
        if fault == "missing"
        else health(
            phase,
            **{
                "stale": {"age_seconds": 6.0},
                "short": {"window_seconds": 1.0},
                "unhealthy": {"business_success": 0.1},
            }[fault],
        )
    )
    changes: dict[str, Any] = {phase: sample}
    if phase == "rollback":
        changes["canary"] = None
    simulator = RolloutSimulator(config(**changes))
    result = simulator.execute("orders")
    assert (
        result.status
        == {"baseline": "blocked", "canary": "recovered", "rollback": "escalated"}[phase]
    )
    assert not any(step.phase == "expanded" for step in result.steps)
    if phase == "baseline":
        assert len(result.steps) == 1 and simulator.state.version == "v1"


def test_exact_thresholds_are_inclusive() -> None:
    bounds = dict(
        error_rate=0.01,
        p95_ms=500.0,
        availability=0.99,
        business_success=0.98,
        window_seconds=60.0,
        age_seconds=5.0,
    )
    result = RolloutSimulator(config(canary=health("canary", **bounds))).execute("orders")
    assert result.status == "expanded"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, True, "0.1"])
def test_invalid_metrics_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        health("canary", error_rate=value)


def test_wrong_service_and_forged_recovery() -> None:
    sim = RolloutSimulator(config(canary=None, rollback_fault="spoofed-success"))
    with pytest.raises(ValueError):
        sim.execute("another")
    result = sim.execute("orders")
    with pytest.raises(ValidationError):
        RolloutResult.model_validate_json(
            result.model_copy(
                update={
                    "status": "recovered",
                    "reason": "canary-unverified",
                }
            ).model_dump_json()
        )


def boundary(
    collector: EvidenceCollector,
    executor: FixtureExecutor,
    grants: ApprovalRegistry,
    simulated: bool = False,
) -> Gateway:
    trusted = context(
        environment="simulated-production" if simulated else "sandbox",
        allowed_checks=["unit_tests", "lint", "typecheck", "build"],
    )
    return Gateway(
        scenario_id="F01",
        context=lambda: trusted,
        executor=executor,
        trace=collector.trace,
        approvals=grants,
    )


def deploy() -> ActionRequest:
    return action(
        "deploy_service",
        environment="simulated-production",
        dry_run=False,
        blast_radius="single_service",
        reversibility="conditional",
    )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("healthy", "expanded"),
        ("missing", "recovered"),
        ("rollback", "escalated"),
        ("baseline", "blocked"),
    ],
)
def test_gateway_authorized_lifecycle_and_replay(tmp_path: Path, fault: str, expected: str) -> None:
    config_changes: dict[str, Any] = {}
    if fault in {"missing", "rollback"}:
        config_changes["canary"] = None
    if fault == "rollback":
        config_changes["rollback_fault"] = "spoofed-success"
    if fault == "baseline":
        config_changes["baseline"] = None
    sim = RolloutSimulator(config(**config_changes))
    docker = FakeDocker()
    executor = FixtureExecutor(snapshot(), runner(docker), simulator=sim)
    collector, grants = EvidenceCollector(tmp_path, "run-1"), ApprovalRegistry()
    request = deploy()
    request = request.model_copy(
        update={"approval_token": grants.issue(request, "run-1", POLICY_VERSION)}
    )
    try:
        gateway = boundary(collector, executor, grants, True)
        receipt = gateway.submit(request)
        assert receipt.state == ("executed" if expected == "expanded" else "failed")
        assert receipt.observation is not None and receipt.observation.rollout is not None
        assert receipt.observation.rollout.status == expected
        assert gateway.submit(request).replayed
        records = replay_trace((tmp_path / "run-1/trace.jsonl").read_bytes())
        observed = next(
            r
            for r in records
            if r.event.actor == "runner" and r.event.claim and '"thresholds"' in r.event.claim
        )
        assert RolloutResult.model_validate_json(observed.event.claim or "").status == expected
        assert any(
            r.event.policy_decision and r.event.policy_decision.decision == "ALLOW"
            for r in records[: observed.event.sequence - 1]
        )
        assert docker.calls == []
        bundle = collector.finalize(
            files={},
            diff="",
            snapshots={
                "rollout": receipt.observation.rollout.model_dump(mode="json"),
            },
        )
        assert bundle.snapshots and not bundle.commands
    finally:
        collector.close()


@pytest.mark.parametrize("fault", ["missing", "expired", "wrong", "dry-run", "audit"])
def test_rollout_not_invoked_without_authorized_dispatch(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sim = RolloutSimulator(config())
    executor = FixtureExecutor(snapshot(), runner(FakeDocker()), simulator=sim)
    collector = EvidenceCollector(tmp_path, "run-1")
    now = [10.0]
    grants = ApprovalRegistry(lambda: now[0])
    request = deploy()
    if fault == "dry-run":
        request = request.model_copy(update={"dry_run": True})
    if fault != "missing":
        token = grants.issue(
            request, "other" if fault == "wrong" else "run-1", POLICY_VERSION, ttl_seconds=1
        )
        request = request.model_copy(update={"approval_token": token})
    if fault == "expired":
        now[0] = 12.0
    if fault == "audit":

        def broken(*args: Any, **kwargs: Any) -> Any:
            raise ValueError("audit unavailable")

        monkeypatch.setattr(collector.trace, "policy_decision", broken)
    try:
        gateway = boundary(collector, executor, grants, True)
        if fault == "audit":
            with pytest.raises(ValueError):
                gateway.submit(request)
        else:
            assert gateway.submit(request).state == ("dry_run" if fault == "dry-run" else "refused")
        assert sim.state.version == "v1" and not sim._used
    finally:
        collector.close()


@pytest.mark.parametrize("check", ["unit_tests", "lint", "typecheck", "build"])
@pytest.mark.parametrize(
    "process,expected",
    [
        (ProcessResult(0), "PASS"),
        (ProcessResult(1, b"all checks passed"), "FAIL"),
        (ProcessResult(-9, status="timeout"), "FAIL"),
        (ProcessResult(1, stderr=b"No module named tool"), "FAIL"),
        (ProcessResult(125), "FAIL"),
    ],
)
def test_check_commands_observed_results(
    tmp_path: Path, check: str, process: ProcessResult, expected: str
) -> None:
    docker = FakeDocker()
    docker.run_result = process
    fixture = snapshot()
    executor = FixtureExecutor(fixture, runner(docker))
    collector = EvidenceCollector(tmp_path, "run-1")
    request = action("run_check", dry_run=False, arguments={"check": check}, target=check)
    try:
        gateway = boundary(collector, executor, ApprovalRegistry())
        receipt = gateway.submit(request)
        assessed = assess_check(request, receipt, collector.trace, fixture.digest)
        assert assessed.status == expected and assessed.events
        assert (
            assess_check(request, receipt, collector.trace, "sha256:" + "b" * 64).status
            == "UNKNOWN"
        )
        argv = next(args for args, _, _ in docker.calls if args[5] == "run")
        assert argv[-1] == check and argv[argv.index("--network") + 1] == "none"
    finally:
        collector.close()


def test_check_suite_and_missing_evidence(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    docker = FakeDocker()
    fixture = snapshot()
    gateway = boundary(collector, FixtureExecutor(fixture, runner(docker)), ApprovalRegistry())
    requests = tuple(
        action(
            "run_check",
            dry_run=False,
            arguments={"check": name},
            target=name,
            action_id=name,
            idempotency_key=name,
        )
        for name in ("unit_tests", "lint", "typecheck", "build")
    )
    try:
        results = run_checks(requests, gateway, collector.trace, fixture.digest)
        assert len(results) == 4 and all(result.status == "PASS" for result in results)
        assert len([call for call in docker.calls if call[0][5] == "run"]) == 4
        receipt = gateway.submit(requests[0])
        forged = receipt.model_copy(
            update={
                "events": (receipt.events[0].model_copy(update={"revision": "sha256:" + "f" * 64}),)
            }
        )
        assert (
            assess_check(requests[0], forged, collector.trace, fixture.digest).status == "UNKNOWN"
        )
        assert (
            assess_check(requests[1], receipt, collector.trace, fixture.digest).status == "UNKNOWN"
        )
        with pytest.raises(ValueError):
            run_checks((requests[0], requests[0]), gateway, collector.trace, fixture.digest)
    finally:
        collector.close()


def test_bootstrap_fixed_commands_do_not_use_fixture_configuration() -> None:
    from agentforge.sandbox.bootstrap import BOOTSTRAP

    compile(BOOTSTRAP, "owned-bootstrap", "exec")  # Compile only, never execute fixture on host.
    assert '"--isolated"' in BOOTSTRAP and '"--config-file=/dev/null"' in BOOTSTRAP
    assert '"--no-isolation"' in BOOTSTRAP and '"PIP_NO_INDEX": "1"' in BOOTSTRAP
    assert 'sys.executable, "-I", "-m"' in BOOTSTRAP
    assert "shell=True" not in BOOTSTRAP


def test_observation_cannot_mix_command_and_rollout() -> None:
    from agentforge.core.schemas import ToolResult
    from agentforge.guardrails.executor import Observation

    with pytest.raises(ValidationError):
        Observation(
            source_snapshot_digest=snapshot().digest,
            rollout=RolloutSimulator(config()).execute("orders"),
            tool_result=ToolResult(
                command_id="check",
                check="lint",
                status="completed",
                exit_code=0,
                stdout="",
                stderr="",
                duration_seconds=0.0,
            ),
        )


def test_post_execution_audit_failure_is_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sim = RolloutSimulator(config())
    collector, grants = EvidenceCollector(tmp_path, "run-1"), ApprovalRegistry()
    executor = FixtureExecutor(snapshot(), runner(FakeDocker()), simulator=sim)
    request = deploy()
    request = request.model_copy(
        update={"approval_token": grants.issue(request, "run-1", POLICY_VERSION)}
    )

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("cannot audit")

    monkeypatch.setattr(collector.trace, "runner_observation", broken)
    try:
        gateway = boundary(collector, executor, grants, True)
        receipt = gateway.submit(request)
        assert receipt.state == "uncertain" and sim.state.version == "v2"
        assert gateway.submit(request).state == "uncertain"
        with pytest.raises(ValueError, match="sealed"):
            gateway.submit(
                request.model_copy(update={"action_id": "new", "idempotency_key": "new"})
            )
    finally:
        collector.close()


def test_absent_simulator_cannot_execute_deployment(tmp_path: Path) -> None:
    collector, grants = EvidenceCollector(tmp_path, "run-1"), ApprovalRegistry()
    fake = FakeDocker()
    executor = FixtureExecutor(snapshot(), runner(fake))
    request = deploy()
    request = request.model_copy(
        update={"approval_token": grants.issue(request, "run-1", POLICY_VERSION)}
    )
    try:
        receipt = boundary(collector, executor, grants, True).submit(request)
        assert receipt.state == "uncertain" and fake.calls == []
    finally:
        collector.close()


def test_suite_refusal_keeps_remaining_checks_unknown(tmp_path: Path) -> None:
    collector, grants = EvidenceCollector(tmp_path, "run-1"), ApprovalRegistry()
    fixture, fake = snapshot(), FakeDocker()
    gateway = boundary(collector, FixtureExecutor(fixture, runner(fake)), grants)
    requests = tuple(
        action(
            "run_check",
            dry_run=False,
            arguments={"check": name},
            target=name,
            action_id=name,
            idempotency_key=name,
            preconditions=["unknown-evidence"],
        )
        for name in ("unit_tests", "lint")
    )
    try:
        results = run_checks(requests, gateway, collector.trace, fixture.digest)
        assert [result.status for result in results] == ["UNKNOWN", "UNKNOWN"]
        assert results[0].events and not results[1].events and not fake.calls
    finally:
        collector.close()


@pytest.mark.parametrize("fault", ["missing", "mismatched", "rollout"])
def test_check_gateway_rejects_invalid_executor_observation(tmp_path: Path, fault: str) -> None:
    from test_gateway import SpyExecutor, gateway

    from agentforge.core.schemas import ToolResult
    from agentforge.guardrails.executor import Observation

    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    fixture = snapshot()
    if fault == "missing":
        spy.result = Observation(source_snapshot_digest=fixture.digest)
    elif fault == "mismatched":
        spy.result = Observation(
            source_snapshot_digest=fixture.digest,
            tool_result=ToolResult(
                command_id="wrong",
                check="build",
                status="completed",
                exit_code=0,
                stdout="passed",
                stderr="",
                duration_seconds=0.0,
            ),
        )
    else:
        spy.result = Observation(
            source_snapshot_digest=fixture.digest,
            rollout=RolloutSimulator(config()).execute("orders"),
        )
    request = action("run_check", dry_run=False)
    try:
        receipt = gateway(collector, spy).submit(request)
        assert receipt.state == "uncertain"
        assert assess_check(request, receipt, collector.trace, fixture.digest).status == "UNKNOWN"
    finally:
        collector.close()
