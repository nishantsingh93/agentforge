"""Run fixed fixture checks through the gateway and verify observed provenance."""

import json
from typing import Literal

from agentforge.core.schemas import ActionRequest, CheckName, Digest, EventRef, Versioned
from agentforge.core.trace import TraceCollector
from agentforge.guardrails.gateway import Gateway, Receipt


class CheckResult(Versioned):
    check: CheckName
    source_snapshot_digest: Digest
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    events: tuple[EventRef, ...]


def assess_check(
    request: ActionRequest,
    receipt: Receipt,
    trace: TraceCollector,
    snapshot_digest: str,
) -> CheckResult:
    """Require receipt refs in the live verified trace, not a claimed success string."""
    request = ActionRequest.model_validate_json(request.model_dump_json())
    receipt = Receipt.model_validate_json(receipt.model_dump_json())
    if request.type != "run_check" or request.arguments.check is None:
        raise ValueError("expected check request")
    status: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
    records = {r.event.event_id: r for r in trace.records}
    refs_valid = all(
        ref.event_id in records and records[ref.event_id].revision == ref.revision
        for ref in receipt.events
    )
    observation = receipt.observation
    if (
        refs_valid
        and receipt.action_id == request.action_id
        and receipt.state in {"executed", "failed"}
        and not request.dry_run
        and observation is not None
        and observation.source_snapshot_digest == snapshot_digest
        and observation.tool_result is not None
        and observation.tool_result.check == request.arguments.check
    ):
        selected = [records[ref.event_id].event for ref in receipt.events]
        tool = observation.tool_result
        proposed = (
            selected[0].action is not None
            and selected[0].action.model_copy(update={"approval_token": None})
            == request.model_copy(update={"approval_token": None})
            and all(
                current.parent_id == previous.event_id
                for previous, current in zip(selected, selected[1:], strict=False)
            )
            and any(event.policy_decision == receipt.decision for event in selected)
        )
        observed = any(
            event.actor == "executor"
            and event.tool_result is not None
            and event.tool_result.command_id == tool.command_id
            and event.tool_result.check == tool.check
            and event.tool_result.status == tool.status
            and event.tool_result.exit_code == tool.exit_code
            for event in selected
        )
        bound = False
        for event in selected:
            if event.actor == "runner" and event.claim is not None:
                try:
                    note = json.loads(event.claim)
                except ValueError:
                    continue
                if isinstance(note, dict) and note == {
                    "action_type": "run_check",
                    "source_snapshot_digest": snapshot_digest,
                    "dispatch_returned": True,
                }:
                    bound = True
        if proposed and observed and bound:
            status = "PASS" if tool.status == "completed" and tool.exit_code == 0 else "FAIL"
    return CheckResult(
        schema_version="1",
        check=request.arguments.check,
        source_snapshot_digest=snapshot_digest,
        status=status,
        events=receipt.events if refs_valid else (),
    )


def run_checks(
    requests: tuple[ActionRequest, ...],
    gateway: Gateway,
    trace: TraceCollector,
    snapshot_digest: str,
) -> tuple[CheckResult, ...]:
    """Caller supplies required checks and scoped requests; no grant minting here."""
    requests = tuple(ActionRequest.model_validate_json(r.model_dump_json()) for r in requests)
    names = [r.arguments.check for r in requests]
    if (
        not requests
        or len(names) != len(set(names))
        or any(r.type != "run_check" or r.dry_run for r in requests)
        or any(name not in {"unit_tests", "lint", "typecheck", "build"} for name in names)
    ):
        raise ValueError("unique supported executable checks required")
    # Validate caller's snapshot identity before any side effects.
    assert requests[0].arguments.check is not None
    CheckResult(
        schema_version="1",
        check=requests[0].arguments.check,
        source_snapshot_digest=snapshot_digest,
        status="UNKNOWN",
        events=(),
    )
    results: list[CheckResult] = []
    stopped = False
    for request in requests:
        if stopped:
            assert request.arguments.check is not None
            results.append(
                CheckResult(
                    schema_version="1",
                    check=request.arguments.check,
                    source_snapshot_digest=snapshot_digest,
                    status="UNKNOWN",
                    events=(),
                )
            )
            continue
        receipt = gateway.submit(request)
        results.append(assess_check(request, receipt, trace, snapshot_digest))
        stopped = receipt.state in {"uncertain", "refused"}
    return tuple(results)
