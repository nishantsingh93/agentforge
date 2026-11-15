"""Real containment tests, explicitly skipped without operator Docker configuration."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from agentforge.core.fixtures import FixtureFile, FixtureSnapshot
from agentforge.sandbox.runner import SandboxConfig, SandboxRunner

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sandbox"


@pytest.fixture
def sandbox() -> SandboxRunner:
    if shutil.which("docker") is None:
        pytest.skip("real Docker isolation unverified: Docker executable unavailable")
    host = os.environ.get("AGENTFORGE_TEST_DOCKER_HOST")
    image = os.environ.get("AGENTFORGE_TEST_IMAGE")
    if not host or not image:
        pytest.skip(
            "set explicit local AGENTFORGE_TEST_DOCKER_HOST and pinned AGENTFORGE_TEST_IMAGE"
        )
    return SandboxRunner(SandboxConfig(host, image, timeout_seconds=5))


def owned_snapshot(name: str, extra: bytes = b"") -> FixtureSnapshot:
    content = (FIXTURES / name).read_bytes() + extra
    file = FixtureFile("test_probe.py", content)
    manifest = [(file.path, hashlib.sha256(content).hexdigest())]
    digest = (
        "sha256:" + hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()
    )
    return FixtureSnapshot(digest, (file,))


def test_real_isolation_and_repeat_runs(
    sandbox: SandboxRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "synthetic-host-marker"
    marker.write_text("owned-synthetic-marker")
    monkeypatch.setenv("AGENTFORGE_SYNTHETIC_SECRET", "synthetic-only")
    extra = (
        "\nclass HostProbe(unittest.TestCase):\n"
        "    def test_host_marker(self):\n"
        f"        self.assertFalse(Path({str(marker)!r}).exists())\n"
    ).encode()
    snapshot = owned_snapshot("isolation.py.txt", extra)
    first = sandbox.run(snapshot)
    second = sandbox.run(snapshot)
    assert first.status == second.status == "completed"
    assert first.exit_code == second.exit_code == 0, (first.stderr, second.stderr)
    assert first.command_id != second.command_id
    assert marker.read_text() == "owned-synthetic-marker"


def test_real_timeout_and_verified_cleanup(sandbox: SandboxRunner) -> None:
    result = sandbox.run(owned_snapshot("timeout.py.txt"))
    assert result.status == "timeout"
    # Runner returns only after an independent successful container-absence query.


def test_real_sandbox_output_is_sanitized_and_replayable(
    sandbox: SandboxRunner, tmp_path: Path
) -> None:
    from agentforge.core.evidence import EvidenceCollector
    from agentforge.core.trace import replay_trace

    extra = (
        b"\nclass EvidenceProbe(unittest.TestCase):\n"
        b"    def test_failure(self):\n"
        b"        print('password=synthetic-integration-secret')\n"
        b"        self.fail('owned intentional failure')\n"
    )
    result = sandbox.run(owned_snapshot("isolation.py.txt", extra))
    assert result.status == "completed" and result.exit_code == 1
    assert "synthetic-integration-secret" in result.stdout
    collector = EvidenceCollector(tmp_path, "integration-run")
    try:
        claim = collector.trace.agent_claim("All tests passed")
        observed = collector.trace.observed_result(result, parent_id=claim.event.event_id)
        bundle = collector.finalize(files={}, diff="", snapshots={})
        assert bundle.commands[0].exit_code == 1
        records = replay_trace(
            (tmp_path / "integration-run/trace.jsonl").read_bytes(), observed.revision
        )
        assert records[0].event.tool_result is None
        assert records[1].event.actor == "executor"
        for path in (tmp_path / "integration-run").rglob("*"):
            if path.is_file():
                assert b"synthetic-integration-secret" not in path.read_bytes()
    finally:
        collector.close()


def test_real_gateway_checks_and_audit(sandbox: SandboxRunner, tmp_path: Path) -> None:
    from agentforge.core.evidence import EvidenceCollector
    from agentforge.core.schemas import ActionRequest, Arguments, Impact
    from agentforge.core.trace import replay_trace
    from agentforge.guardrails.approvals import ApprovalRegistry
    from agentforge.guardrails.executor import FixtureExecutor
    from agentforge.guardrails.gateway import Gateway
    from agentforge.guardrails.taxonomy import PolicyContext, RiskTier

    extra = (
        b"\nclass GatewayProbe(unittest.TestCase):\n"
        b"    def test_failure(self):\n"
        b"        print('password=synthetic-gateway-secret')\n"
        b"        self.fail('intentional owned failure')\n"
    )
    executor = FixtureExecutor(owned_snapshot("isolation.py.txt", extra), sandbox)
    collector = EvidenceCollector(tmp_path, "gateway-run")
    trusted = PolicyContext(
        schema_version="1",
        run_id="gateway-run",
        scenario_id="F01",
        environment="sandbox",
        allowed_files=("test_probe.py",),
        allowed_services=(),
        allowed_checks=("unit_tests",),
        protected_paths=(),
        minimum_risk=RiskTier.LOW,
        isolation_verified=True,
        tests_passed=None,
        baseline_healthy=None,
        rollback_ready=None,
    )
    request = ActionRequest(
        schema_version="1",
        action_id="check-1",
        type="run_check",
        arguments=Arguments(check="unit_tests"),
        target="unit_tests",
        environment="sandbox",
        requested_capabilities=("check",),
        blast_radius="single_file",
        reversibility="reversible",
        impact=Impact(availability="none", data="none", revenue="none", security="none"),
        preconditions=(),
        approval_token=None,
        idempotency_key="check-1",
        dry_run=False,
    )
    try:
        boundary = Gateway(
            scenario_id="F01",
            context=lambda: trusted,
            executor=executor,
            trace=collector.trace,
            approvals=ApprovalRegistry(),
        )
        receipt = boundary.submit(request)
        assert receipt.state == "failed"
        assert receipt.observation is not None and receipt.observation.tool_result is not None
        assert receipt.observation.tool_result.exit_code == 1
        assert "synthetic-gateway-secret" in receipt.observation.tool_result.stdout
        count = len(collector.trace.records)
        replayed = boundary.submit(request)
        assert replayed.replayed and replayed.events == receipt.events
        assert len(collector.trace.records) == count
        bundle = collector.finalize(files={}, diff="", snapshots={})
        assert len(bundle.commands) == 1 and bundle.commands[0].exit_code == 1
        records = replay_trace((tmp_path / "gateway-run/trace.jsonl").read_bytes())
        result_index = next(i for i, r in enumerate(records) if r.event.tool_result is not None)
        assert any(
            r.event.policy_decision and r.event.policy_decision.decision == "ALLOW"
            for r in records[:result_index]
        )
        for path in (tmp_path / "gateway-run").rglob("*"):
            if path.is_file():
                assert b"synthetic-gateway-secret" not in path.read_bytes()
    finally:
        collector.close()
