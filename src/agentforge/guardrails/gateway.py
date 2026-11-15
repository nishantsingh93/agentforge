"""Single-process action boundary: policy and audit precede all dispatch."""

import hashlib
from collections.abc import Callable
from threading import Lock
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentforge.core.schemas import ActionRequest, EventRef, Identifier, PolicyDecision, Versioned
from agentforge.core.trace import TraceCollector, TraceRecord, canonical_json
from agentforge.guardrails.approvals import ApprovalError, ApprovalRegistry, request_binding
from agentforge.guardrails.executor import Executor, Observation
from agentforge.guardrails.policy import evaluate
from agentforge.guardrails.taxonomy import PolicyContext


class GatewayError(ValueError):
    """Rejected request, audit failure, conflict or sealed gateway."""


class Receipt(Versioned):
    action_id: Identifier
    decision: PolicyDecision
    state: Literal["refused", "dry_run", "executed", "failed", "uncertain"]
    observation: Observation | None
    events: Annotated[tuple[EventRef, ...], Field(min_length=1)]
    replayed: bool = False

    @model_validator(mode="after")
    def consistent_receipt(self) -> Self:
        if self.action_id != self.decision.action_id:
            raise ValueError("receipt action mismatch")
        if self.state == "refused":
            if self.decision.decision == "ALLOW" or self.observation is not None:
                raise ValueError("refusal cannot carry authorization or execution")
        elif self.decision.decision != "ALLOW":
            raise ValueError("dispatch states require authorization")
        if self.state == "dry_run" and self.observation is not None:
            raise ValueError("dry run cannot carry execution")
        if self.state in {"executed", "failed"}:
            if self.observation is None:
                raise ValueError("completed dispatch requires observation")
            result = self.observation.tool_result
            failed = result is not None and (result.status != "completed" or result.exit_code != 0)
            failed = failed or (
                self.observation.rollout is not None
                and self.observation.rollout.status != "expanded"
            )
            if (self.state == "failed") != failed:
                raise ValueError("receipt state contradicts observed command result")
        return self


def _ref(record: TraceRecord) -> EventRef:
    return EventRef(kind="event", event_id=record.event.event_id, revision=record.revision)


class Gateway:
    def __init__(
        self,
        *,
        scenario_id: str,
        context: Callable[[], PolicyContext],
        executor: Executor,
        trace: TraceCollector,
        approvals: ApprovalRegistry,
    ) -> None:
        self._scenario_id = scenario_id
        self._context = context
        self._executor = executor
        self._trace = trace
        self._approvals = approvals
        self._lock = Lock()
        self._sealed = False
        self._entries: dict[str, tuple[str, Receipt | None]] = {}
        self._action_ids: dict[str, str] = {}

    def _fresh(self) -> PolicyContext:
        context = PolicyContext.model_validate_json(self._context().model_dump_json())
        if context.run_id != self._trace.run_id or context.scenario_id != self._scenario_id:
            raise GatewayError("trusted context identity mismatch")
        return context

    def submit(self, request: ActionRequest) -> Receipt:
        if not self._lock.acquire(blocking=False):
            raise GatewayError("gateway operation already in flight")
        try:
            return self._submit(request)
        finally:
            self._lock.release()

    def _submit(self, request: ActionRequest) -> Receipt:
        try:
            request = ActionRequest.model_validate_json(request.model_dump_json())
            binding = request_binding(request, include_token=True)
        except (ValueError, TypeError, AttributeError):
            raise GatewayError("invalid action contract") from None
        key = request.idempotency_key
        if key in self._entries:
            previous, receipt = self._entries[key]
            if binding != previous:
                raise GatewayError("idempotency key conflicts with earlier payload")
            if receipt is None:
                raise GatewayError("earlier attempt is incomplete; no automatic retry")
            # Replay is historical evidence, never a new authorization or dispatch.
            return Receipt.model_validate_json(
                receipt.model_copy(update={"replayed": True}).model_dump_json()
            )
        if self._sealed:
            raise GatewayError("gateway sealed after uncertain operation")
        if request.action_id in self._action_ids:
            raise GatewayError("action identifier already used with another key")
        self._entries[key] = (binding, None)
        self._action_ids[request.action_id] = key
        events: list[EventRef] = []
        dispatched = False
        decision: PolicyDecision | None = None
        observation: Observation | None = None

        def record_policy(value: PolicyDecision) -> None:
            events.append(
                _ref(self._trace.policy_decision(request, value, parent_id=events[-1].event_id))
            )

        def derived(verdict: Literal["ALLOW", "BLOCK"], rule: str) -> PolicyDecision:
            assert decision is not None
            return PolicyDecision(
                schema_version="1",
                decision_id="gateway-"
                + hashlib.sha256(
                    f"{self._trace.run_id}:{request.action_id}:{rule}:{len(events)}".encode()
                ).hexdigest(),
                action_id=request.action_id,
                decision=verdict,
                rule_ids=(rule,),
                policy_version=decision.policy_version,
                reason=rule.replace("-", " "),
                allowed_scope=(request.target,) if verdict == "ALLOW" else (),
            )

        def finish(
            state: Literal["refused", "dry_run", "executed", "failed", "uncertain"],
        ) -> Receipt:
            assert decision is not None
            receipt = Receipt(
                schema_version="1",
                action_id=request.action_id,
                decision=decision,
                state=state,
                observation=observation,
                events=tuple(events),
            )
            self._entries[key] = (binding, receipt)
            return receipt

        try:
            events.append(_ref(self._trace.proposed_action(request)))
            decision = evaluate(request, self._fresh()).decision
            record_policy(decision)
            if decision.decision in {"BLOCK", "ESCALATE"}:
                return finish("refused")
            if (
                request.type not in {"read_file", "edit_file", "run_check", "deploy_service"}
                or (
                    request.type == "run_check"
                    and request.arguments.check not in {"unit_tests", "lint", "typecheck", "build"}
                )
                or (
                    request.type == "deploy_service"
                    and request.environment != "simulated-production"
                )
            ):
                decision = derived("BLOCK", "unsupported-operation")
                record_policy(decision)
                return finish("refused")
            # Refresh after initial audit, immediately before dispatch authorization.
            dispatch_context = self._fresh()
            decision = evaluate(request, dispatch_context).decision
            record_policy(decision)
            if decision.decision in {"BLOCK", "ESCALATE"}:
                return finish("refused")
            needs_approval = decision.decision == "REQUIRE_APPROVAL"
            if needs_approval:
                try:
                    self._approvals.validate(request, self._trace.run_id, decision.policy_version)
                except ApprovalError:
                    decision = derived("BLOCK", "invalid-synthetic-approval")
                    record_policy(decision)
                    return finish("refused")
                decision = derived("ALLOW", "validated-synthetic-approval")
                record_policy(decision)
            if request.dry_run:
                events.append(
                    _ref(
                        self._trace.runner_observation(
                            "dry_run: no executor invoked", parent_id=events[-1].event_id
                        )
                    )
                )
                return finish("dry_run")
            # Audit writes may take time. Require the complete trusted snapshot to
            # remain unchanged after the final authorization audit, before dispatch.
            if self._fresh() != dispatch_context:
                decision = derived("BLOCK", "context-changed-before-dispatch")
                record_policy(decision)
                return finish("refused")
            if needs_approval:
                try:
                    # Recheck expiry after audit writes; consume once, before the side effect.
                    self._approvals.validate(
                        request, self._trace.run_id, decision.policy_version, consume=True
                    )
                except ApprovalError:
                    decision = derived("BLOCK", "expired-synthetic-approval")
                    record_policy(decision)
                    return finish("refused")
            dispatched = True
            raw = self._executor.execute(request)
            observation = Observation.model_validate_json(raw.model_dump_json())
            if request.type != "deploy_service" and observation.rollout is not None:
                raise GatewayError("unexpected rollout observation")
            if request.type == "deploy_service":
                if (
                    observation.rollout is None
                    or observation.rollout.service != request.target
                    or observation.tool_result is not None
                    or observation.content is not None
                ):
                    raise GatewayError("mismatched rollout observation")
                events.append(
                    _ref(
                        self._trace.runner_observation(
                            observation.rollout.model_dump_json(), parent_id=events[-1].event_id
                        )
                    )
                )
            elif request.type == "run_check":
                if (
                    observation.tool_result is None
                    or observation.tool_result.check != request.arguments.check
                ):
                    raise GatewayError("executor returned mismatched observation")
            elif observation.tool_result is not None:
                raise GatewayError("file operation cannot claim a command result")
            elif request.type == "read_file" and observation.content is None:
                raise GatewayError("read observation missing content")
            if observation.tool_result is not None:
                events.append(
                    _ref(
                        self._trace.observed_result(
                            observation.tool_result, parent_id=events[-1].event_id
                        )
                    )
                )
            events.append(
                _ref(
                    self._trace.runner_observation(
                        canonical_json(
                            {
                                "action_type": request.type,
                                "source_snapshot_digest": observation.source_snapshot_digest,
                                "dispatch_returned": True,
                            }
                        ).decode(),
                        parent_id=events[-1].event_id,
                    )
                )
            )
            result = observation.tool_result
            state: Literal["executed", "failed"] = (
                "failed"
                if (result is not None and (result.status != "completed" or result.exit_code != 0))
                or (observation.rollout is not None and observation.rollout.status != "expanded")
                else "executed"
            )
            return finish(state)
        except Exception:
            self._sealed = True
            if dispatched and decision is not None:
                # Never echo an executor exception (it may contain raw input). Retain
                # actual observations if available; an audit failure remains uncertain.
                try:
                    events.append(
                        _ref(
                            self._trace.runner_observation(
                                "uncertain: dispatch or post-execution audit failed; do not retry",
                                parent_id=events[-1].event_id,
                            )
                        )
                    )
                except Exception:
                    pass  # Receipt explicitly preserves uncertainty and last durable refs.
                return finish("uncertain")
            raise GatewayError(
                "gateway stopped before dispatch; audit or context unavailable"
            ) from None
        except BaseException:
            # Cancellation may interrupt dispatch. Preserve the incomplete slot and
            # seal the run; never retry under another key after an unknown outcome.
            self._sealed = True
            raise
