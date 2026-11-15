"""Actual seeded fixture code runs only through the gateway and Docker sandbox."""

from functools import partial
from pathlib import Path

import pytest
from test_sandbox_integration import sandbox  # noqa: F401

from agentforge.core.evidence import EvidenceCollector
from agentforge.core.schemas import ActionRequest, Arguments, Impact
from agentforge.evaluation.outcome import classify_outcome
from agentforge.guardrails.approvals import ApprovalRegistry
from agentforge.guardrails.executor import FixtureExecutor
from agentforge.guardrails.gateway import Gateway
from agentforge.guardrails.taxonomy import PolicyContext, RiskTier
from agentforge.lab.seeds import load_seeds, prepare
from agentforge.sandbox.runner import SandboxRunner

ROOT = Path(__file__).resolve().parents[2]


def request(index: int, path: str | None = None, content: str | None = None) -> ActionRequest:
    return ActionRequest(
        schema_version="1",
        action_id=f"action-{index}",
        type="run_check" if path is None else "edit_file",
        arguments=Arguments(check="unit_tests")
        if path is None
        else Arguments(path=path, content=content),
        target="unit_tests" if path is None else path,
        environment="sandbox",
        requested_capabilities=("check",) if path is None else ("write",),
        blast_radius="single_file",
        reversibility="reversible",
        impact=Impact(availability="none", data="none", revenue="none", security="none"),
        preconditions=(),
        approval_token=None,
        idempotency_key=f"key-{index}",
        dry_run=False,
    )


@pytest.mark.parametrize("sid", ["F01", "F02", "F04", "F06"])
def test_real_seed_fault_and_repair(sandbox: SandboxRunner, tmp_path: Path, sid: str) -> None:  # noqa: F811
    seed = next(s for s in load_seeds(ROOT) if s.registered.scenario.id == sid)
    base = {f.path: f.content.decode() for f in seed.registered.fixture.files}
    source = "orders.py" if sid == "F01" else "service.py"
    # Different final bundles: earlier failing attempts are never silently erased
    # from a single run. AF-014 owns retry/run orchestration.
    modes = ("fault", "repair", "weaken") if sid == "F04" else ("fault", "repair")
    for mode in modes:
        collector = EvidenceCollector(tmp_path, mode)
        initial = prepare(seed).snapshot
        executor = FixtureExecutor(initial, sandbox)
        context = PolicyContext(
            schema_version="1",
            run_id=mode,
            scenario_id=sid,
            environment="sandbox",
            allowed_files=tuple(f.path for f in initial.files),
            allowed_services=(),
            allowed_checks=("unit_tests",),
            protected_paths=(),
            minimum_risk=RiskTier.LOW,
            isolation_verified=True,
            tests_passed=None,
            baseline_healthy=None,
            rollback_ready=None,
        )
        boundary = Gateway(
            scenario_id=sid,
            context=partial(lambda value: value, context),
            executor=executor,
            trace=collector.trace,
            approvals=ApprovalRegistry(),
        )
        try:
            if mode == "repair":
                assert boundary.submit(request(1, source, base[source])).state == "executed"
            elif mode == "weaken":
                weakened = base["test_orders.py"].split("    def test_invalid")[0]
                assert boundary.submit(request(1, "test_orders.py", weakened)).state == "executed"
            receipt = boundary.submit(request(2))
            assert receipt.observation is not None and receipt.observation.tool_result is not None
            tool = receipt.observation.tool_result
            assert tool.status == "completed", (tool.stdout, tool.stderr)
            assert (tool.exit_code == 0) == (mode != "fault"), (tool.stdout, tool.stderr)
            if sid == "F04" and mode == "weaken":
                files = {f.path: f.content for f in executor.snapshot.files}
                bundle = collector.finalize(
                    files={p: c.decode() for p, c in files.items()}, diff="", snapshots={}
                )
                outcome = classify_outcome(
                    scenario=seed.registered.scenario,
                    profile=seed.profile,
                    evidence=bundle,
                    files=files,
                    trace=(tmp_path / mode / "trace.jsonl").read_bytes(),
                )
                assert outcome.outcome is not None and outcome.outcome.category == "Misleading"
        finally:
            collector.close()
        # Every invocation returns only after SandboxRunner's cleanup verification.
        assert prepare(seed).snapshot == initial
