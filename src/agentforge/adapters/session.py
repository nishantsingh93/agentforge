"""Trusted adapter driver; execution and execution audit belong to the gateway."""

from typing import Protocol

from agentforge.adapters.base import AdapterPlan, AdapterTask, AgentAdapter
from agentforge.core.schemas import ActionRequest, PolicyDecision
from agentforge.core.trace import TraceCollector
from agentforge.guardrails.gateway import Receipt


class SubmissionGateway(Protocol):
    def submit(self, request: ActionRequest) -> PolicyDecision | Receipt: ...


class AdapterError(ValueError):
    """Malformed adapter output or mismatched gateway response."""


def run_adapter(
    adapter: AgentAdapter,
    task: AdapterTask,
    gateway: SubmissionGateway,
    trace: TraceCollector,
) -> tuple[PolicyDecision | Receipt, ...]:
    """Record proposals/claims, then submit in order; stop on any non-ALLOW decision.

    An ALLOW response is not proof of execution. Only trusted executor wiring can
    record a ToolResult. Test gateways may be read-only decision stubs.
    """
    task = AdapterTask.model_validate_json(task.model_dump_json())
    try:
        plan = AdapterPlan.model_validate_json(adapter.propose(task).model_dump_json())
    except (ValueError, TypeError, AttributeError):
        raise AdapterError("invalid adapter plan") from None
    parent = trace.agent_claim(plan.claim).event.event_id
    decisions: list[PolicyDecision | Receipt] = []
    for request in plan.requests:
        proposed = trace.proposed_action(request, parent_id=parent)
        response = gateway.submit(request)
        if isinstance(response, Receipt):
            try:
                receipt = Receipt.model_validate_json(response.model_dump_json())
                if (
                    receipt.action_id != request.action_id
                    or receipt.decision.action_id != request.action_id
                ):
                    raise ValueError("mismatched receipt")
                records = {r.event.event_id: r for r in trace.records}
                if not receipt.events or any(
                    ref.event_id not in records or records[ref.event_id].revision != ref.revision
                    for ref in receipt.events
                ):
                    raise ValueError("unverifiable receipt")
            except (ValueError, TypeError, AttributeError):
                raise AdapterError("invalid gateway receipt") from None
            decisions.append(receipt)
            parent = receipt.events[-1].event_id
            if receipt.state not in {"executed", "dry_run"}:
                break
            continue
        decision = response
        try:
            decision = PolicyDecision.model_validate_json(decision.model_dump_json())
            if decision.action_id != request.action_id:
                raise ValueError("mismatched action")
        except (ValueError, TypeError, AttributeError):
            raise AdapterError("invalid gateway decision") from None
        parent = trace.policy_decision(
            request, decision, parent_id=proposed.event.event_id
        ).event.event_id
        decisions.append(decision)
        if decision.decision != "ALLOW":
            break
    return tuple(decisions)
