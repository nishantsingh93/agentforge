"""Dispatch boundary tests. Spy execution is not real Docker containment."""

from pathlib import Path
from typing import Any

import pytest
from test_policy import action, context
from test_sandbox import FakeDocker, runner, snapshot

from agentforge.adapters.base import AdapterPlan, AdapterTask
from agentforge.adapters.session import run_adapter
from agentforge.core.evidence import EvidenceCollector
from agentforge.core.fixtures import FixtureFile
from agentforge.core.schemas import ActionRequest, ToolResult
from agentforge.core.trace import TraceError, replay_trace
from agentforge.guardrails.approvals import ApprovalRegistry
from agentforge.guardrails.executor import FixtureExecutor, Observation
from agentforge.guardrails.gateway import Gateway, GatewayError, Receipt
from agentforge.guardrails.policy import POLICY_VERSION
from agentforge.guardrails.taxonomy import PolicyContext
from agentforge.sandbox.runner import ProcessResult


class SpyExecutor:
    def __init__(self) -> None:
        self.calls: list[ActionRequest] = []
        self.failure: Exception | None = None
        self.result = Observation(source_snapshot_digest="sha256:" + "a" * 64, content="owned")

    def execute(self, request: ActionRequest) -> Observation:
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


def gateway(
    collector: EvidenceCollector,
    executor: SpyExecutor,
    trusted: PolicyContext | None = None,
    grants: ApprovalRegistry | None = None,
) -> Gateway:
    return Gateway(
        scenario_id="F01",
        context=lambda: trusted if trusted is not None else context(),
        executor=executor,
        trace=collector.trace,
        approvals=grants if grants is not None else ApprovalRegistry(),
    )


@pytest.mark.parametrize(
    "kind,changes,ctx",
    [
        ("delete_data", {}, {}),
        ("edit_authentication", {}, {}),
        ("read_file", {"target": "outside"}, {}),
        ("read_file", {}, {"isolation_verified": None}),
        ("read_file", {"preconditions": ["unknown"]}, {}),
        ("edit_file", {}, {"minimum_risk": 2}),
        ("edit_file", {"approval_token": "fake"}, {"minimum_risk": 2}),
        ("deploy_service", {}, {}),
        (
            "run_check",
            {"arguments": {"check": "contract_tests"}, "target": "contract_tests"},
            {"allowed_checks": ["contract_tests"]},
        ),
    ],
)
def test_refusal_never_calls_executor(
    tmp_path: Path, kind: str, changes: dict[str, Any], ctx: dict[str, Any]
) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    try:
        result = gateway(collector, spy, context(**ctx)).submit(
            action(kind, dry_run=False, **changes)
        )
        assert result.state == "refused" and spy.calls == []
        assert result.events and result.decision.decision != "ALLOW"
    finally:
        collector.close()


def test_valid_approval_original_requirement_and_redacted_audit(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy, grants = SpyExecutor(), ApprovalRegistry()
    request = action("edit_file", dry_run=False)
    token = grants.issue(request, "run-1", POLICY_VERSION)
    request = request.model_copy(update={"approval_token": token})
    try:
        boundary = gateway(collector, spy, context(minimum_risk=2), grants)
        receipt = boundary.submit(request)
        assert receipt.state == "executed" and len(spy.calls) == 1
        assert boundary.submit(request).replayed
        assert len(spy.calls) == 1
        records = collector.trace.records
        assert any(
            r.event.policy_decision and r.event.policy_decision.decision == "REQUIRE_APPROVAL"
            for r in records
        )
        assert any(
            r.event.policy_decision
            and "validated-synthetic-approval" in r.event.policy_decision.rule_ids
            for r in records
        )
        assert token.encode() not in (tmp_path / "run-1/trace.jsonl").read_bytes()
        assert records[0].event.action is not None
        assert records[0].event.action.approval_token == "REDACTED"
    finally:
        collector.close()


def test_dry_run_does_not_dispatch_or_consume(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy, grants = SpyExecutor(), ApprovalRegistry()
    request = action("edit_file", dry_run=True)
    token = grants.issue(request, "run-1", POLICY_VERSION)
    request = request.model_copy(update={"approval_token": token})
    try:
        receipt = gateway(collector, spy, context(minimum_risk=2), grants).submit(request)
        assert receipt.state == "dry_run" and spy.calls == []
        grants.validate(request, "run-1", POLICY_VERSION)
    finally:
        collector.close()


def test_context_changed_before_dispatch(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    contexts = iter((context(), context(allowed_files=[])))
    boundary = Gateway(
        scenario_id="F01",
        context=contexts.__next__,
        executor=spy,
        trace=collector.trace,
        approvals=ApprovalRegistry(),
    )
    try:
        receipt = boundary.submit(action(dry_run=False))
        assert receipt.state == "refused" and spy.calls == []
    finally:
        collector.close()


@pytest.mark.parametrize("stage", ["proposed_action", "policy_decision"])
def test_preexecution_audit_failure_blocks_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()

    def broken(*args: object, **kwargs: object) -> None:
        raise TraceError("synthetic fault")

    monkeypatch.setattr(collector.trace, stage, broken)
    try:
        boundary = gateway(collector, spy)
        with pytest.raises(GatewayError):
            boundary.submit(action(dry_run=False))
        assert spy.calls == []
        with pytest.raises(GatewayError):
            boundary.submit(action(dry_run=False))
    finally:
        collector.close()


@pytest.mark.parametrize("fault", ["executor", "audit"])
def test_uncertainty_seals_without_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    if fault == "executor":
        spy.failure = RuntimeError("raw-secret-must-not-appear")
    else:

        def broken(*args: object, **kwargs: object) -> None:
            raise TraceError("write failed")

        monkeypatch.setattr(collector.trace, "runner_observation", broken)
    try:
        boundary = gateway(collector, spy)
        request = action(dry_run=False)
        receipt = boundary.submit(request)
        assert receipt.state == "uncertain" and len(spy.calls) == 1
        assert boundary.submit(request).state == "uncertain"
        assert len(spy.calls) == 1
        with pytest.raises(GatewayError, match="sealed"):
            boundary.submit(action(dry_run=False, action_id="second", idempotency_key="second"))
        assert b"raw-secret-must-not-appear" not in (tmp_path / "run-1/trace.jsonl").read_bytes()
    finally:
        collector.close()


def test_idempotency_and_action_identity_conflicts(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    try:
        boundary = gateway(collector, spy)
        request = action(dry_run=False)
        assert boundary.submit(request).state == "executed"
        with pytest.raises(GatewayError, match="conflicts"):
            boundary.submit(request.model_copy(update={"dry_run": True}))
        with pytest.raises(GatewayError, match="identifier"):
            boundary.submit(request.model_copy(update={"idempotency_key": "new"}))
        assert len(spy.calls) == 1
    finally:
        collector.close()


@pytest.mark.parametrize("status,code", [("completed", 1), ("timeout", None), ("error", 125)])
def test_observed_failure_is_not_success(tmp_path: Path, status: str, code: int | None) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    spy.result = Observation(
        source_snapshot_digest="sha256:" + "a" * 64,
        tool_result=ToolResult.model_validate(
            dict(
                command_id="cmd",
                check="unit_tests",
                status=status,
                exit_code=code,
                stdout="password=synthetic",
                stderr="",
                duration_seconds=0.1,
            )
        ),
    )
    try:
        receipt = gateway(collector, spy).submit(action("run_check", dry_run=False))
        assert receipt.state == "failed"
        assert collector.trace.records[-2].event.tool_result is not None
        assert b"synthetic" not in (tmp_path / "run-1/trace.jsonl").read_bytes()
    finally:
        collector.close()


def test_fixture_snapshot_edit_read_and_fake_sandbox_pipeline(tmp_path: Path) -> None:
    original = snapshot((FixtureFile("orders.py", b"old"),))
    docker = FakeDocker()
    docker.run_result = ProcessResult(1, b"failed", b"")
    executor = FixtureExecutor(original, runner(docker))
    collector = EvidenceCollector(tmp_path, "run-1")
    boundary = Gateway(
        scenario_id="F01",
        context=context,
        executor=executor,
        trace=collector.trace,
        approvals=ApprovalRegistry(),
    )
    try:
        boundary.submit(action("edit_file", dry_run=False))
        assert original.files[0].content == b"old"
        assert executor.snapshot.files[0].content == b"proposed"
        assert executor.snapshot.digest != original.digest
        read = boundary.submit(action(dry_run=False, action_id="read-2", idempotency_key="read-2"))
        assert read.observation is not None and read.observation.content == "proposed"
        check = boundary.submit(
            action("run_check", dry_run=False, action_id="check-3", idempotency_key="check-3")
        )
        assert check.state == "failed"
        assert any(call[0][5] == "run" for call in docker.calls)
        replay_trace((tmp_path / "run-1/trace.jsonl").read_bytes())
    finally:
        collector.close()


def test_adapter_consumes_receipt_and_stops_on_failure(tmp_path: Path) -> None:
    class Adapter:
        def propose(self, task: AdapterTask) -> AdapterPlan:
            return AdapterPlan(
                schema_version="1",
                claim="All tests passed",
                requests=(
                    action("run_check", dry_run=False),
                    action(dry_run=False, action_id="later", idempotency_key="later"),
                ),
            )

    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    spy.failure = RuntimeError("executor unavailable")
    try:
        receipts = run_adapter(
            Adapter(),
            AdapterTask(
                schema_version="1",
                task_id="task",
                scenario_id="F01",
                instruction="do work",
                source="",
            ),
            gateway(collector, spy),
            collector.trace,
        )
        assert len(receipts) == 1 and isinstance(receipts[0], Receipt)
        assert receipts[0].state == "uncertain" and len(spy.calls) == 1
        assert collector.trace.records[0].event.actor == "agent"
    finally:
        collector.close()


@pytest.mark.parametrize(
    "fault", ["expired", "wrong-run", "wrong-version", "wrong-content", "used"]
)
def test_invalid_grant_never_dispatches(tmp_path: Path, fault: str) -> None:
    now = [100.0]
    grants = ApprovalRegistry(lambda: now[0])
    request = action("edit_file", dry_run=False)
    token = grants.issue(
        request,
        "other" if fault == "wrong-run" else "run-1",
        "wrong" if fault == "wrong-version" else POLICY_VERSION,
        ttl_seconds=1,
    )
    request = request.model_copy(update={"approval_token": token})
    if fault == "expired":
        now[0] = 101.0
    if fault == "wrong-content":
        request = request.model_copy(
            update={"arguments": request.arguments.model_copy(update={"content": "changed"})}
        )
    if fault == "used":
        grants.validate(request, "run-1", POLICY_VERSION, consume=True)
    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    try:
        result = gateway(collector, spy, context(minimum_risk=2), grants).submit(request)
        assert result.state == "refused" and spy.calls == []
    finally:
        collector.close()


def test_expiry_during_approval_audit_prevents_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100.0]
    grants = ApprovalRegistry(lambda: now[0])
    request = action("edit_file", dry_run=False)
    token = grants.issue(request, "run-1", POLICY_VERSION, ttl_seconds=1)
    request = request.model_copy(update={"approval_token": token})
    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    original = collector.trace.policy_decision
    from agentforge.core.schemas import PolicyDecision
    from agentforge.core.trace import TraceRecord

    def delayed(
        action: ActionRequest, decision: PolicyDecision, *, parent_id: str | None = None
    ) -> TraceRecord:
        result = original(action, decision, parent_id=parent_id)
        if "validated-synthetic-approval" in decision.rule_ids:
            now[0] = 101.0
        return result

    monkeypatch.setattr(collector.trace, "policy_decision", delayed)
    try:
        receipt = gateway(collector, spy, context(minimum_risk=2), grants).submit(request)
        assert receipt.state == "refused" and spy.calls == []
        assert "expired-synthetic-approval" in receipt.decision.rule_ids
    finally:
        collector.close()


def test_final_context_change_and_wrong_run_fail_closed(tmp_path: Path) -> None:
    for index, values in enumerate(
        ((context(), context(), context(isolation_verified=False)), (context(run_id="wrong"),))
    ):
        root = tmp_path / str(index)
        root.mkdir()
        collector, spy = EvidenceCollector(root, "run-1"), SpyExecutor()
        contexts = iter(values)
        boundary = Gateway(
            scenario_id="F01",
            context=contexts.__next__,
            executor=spy,
            trace=collector.trace,
            approvals=ApprovalRegistry(),
        )
        try:
            if index == 0:
                assert boundary.submit(action(dry_run=False)).state == "refused"
            else:
                with pytest.raises(GatewayError):
                    boundary.submit(action(dry_run=False))
            assert spy.calls == []
        finally:
            collector.close()


def test_unsupported_operation_with_valid_grant_still_refused(tmp_path: Path) -> None:
    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    registry = ApprovalRegistry()
    request = action("deploy_service", dry_run=False)
    token = registry.issue(request, "run-1", POLICY_VERSION)
    try:
        result = gateway(collector, spy, context(), registry).submit(
            request.model_copy(update={"approval_token": token})
        )
        assert result.state == "refused" and spy.calls == []
        assert "unsupported-operation" in result.decision.rule_ids
    finally:
        collector.close()


def test_invalid_request_and_inflight_request_do_not_dispatch(tmp_path: Path) -> None:
    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    try:
        boundary = gateway(collector, spy)
        with pytest.raises(GatewayError, match="invalid"):
            boundary.submit(action().model_copy(update={"type": "shell"}))
        assert collector.trace.records == ()
        assert boundary._lock.acquire(blocking=False)
        try:
            with pytest.raises(GatewayError, match="in flight"):
                boundary.submit(action(dry_run=False))
        finally:
            boundary._lock.release()
        assert spy.calls == []
    finally:
        collector.close()


def test_executor_candidate_validation_preserves_original_snapshot() -> None:
    original = snapshot((FixtureFile("orders.py", b"original"),))
    executor = FixtureExecutor(original, runner(FakeDocker()))
    # One million Unicode characters fit the schema but exceed the byte limit.
    request = action(
        "edit_file", dry_run=False, arguments={"path": "orders.py", "content": "α" * 600_000}
    )
    with pytest.raises(ValueError):
        executor.execute(request)
    assert executor.snapshot == original
    with pytest.raises(ValueError):
        executor.execute(action("edit_file", dry_run=True))
    assert executor.snapshot == original


def test_receipt_rejects_invented_success(tmp_path: Path) -> None:
    from pydantic import ValidationError

    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()
    try:
        receipt = gateway(collector, spy).submit(action(dry_run=True))
        forged = receipt.model_copy(update={"state": "executed"})
        with pytest.raises(ValidationError):
            Receipt.model_validate_json(forged.model_dump_json())
        forged = receipt.model_copy(update={"action_id": "other"})
        with pytest.raises(ValidationError):
            Receipt.model_validate_json(forged.model_dump_json())
    finally:
        collector.close()


def test_interrupted_dispatch_seals_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, spy = EvidenceCollector(tmp_path, "run-1"), SpyExecutor()

    def interrupted(request: ActionRequest) -> Observation:
        spy.calls.append(request)
        raise KeyboardInterrupt

    monkeypatch.setattr(spy, "execute", interrupted)
    try:
        boundary = gateway(collector, spy)
        request = action(dry_run=False)
        with pytest.raises(KeyboardInterrupt):
            boundary.submit(request)
        with pytest.raises(GatewayError, match="incomplete"):
            boundary.submit(request)
        with pytest.raises(GatewayError, match="sealed"):
            boundary.submit(action(dry_run=False, action_id="other", idempotency_key="other"))
        assert len(spy.calls) == 1
    finally:
        collector.close()
