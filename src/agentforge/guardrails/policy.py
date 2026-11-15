"""Approved AF-007 policy: pure decisions, no execution or token validation."""

import hashlib
import json
from typing import Any

from agentforge.core.schemas import ActionRequest, Contract, PolicyDecision
from agentforge.guardrails.classifier import classify
from agentforge.guardrails.taxonomy import PolicyContext, RiskTier

POLICY_VERSION = "sandbox-policy-v1"
CAPABILITIES = {
    "read_file": ("read",),
    "edit_file": ("write",),
    "run_check": ("check",),
    "deploy_service": ("deploy",),
    "delete_data": ("delete",),
    "edit_authentication": ("auth",),
}


class PolicyInputError(ValueError):
    """Malformed input is rejected without inventing a valid action or audit ID."""


class Evaluation(Contract):
    risk: RiskTier
    decision: PolicyDecision


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyInputError("duplicate action key")
        result[key] = value
    return result


def evaluate_json(payload: str, context: PolicyContext | None) -> Evaluation:
    try:
        if len(payload.encode()) > 2_097_152:
            raise PolicyInputError("action payload too large")
        parsed = json.loads(payload, object_pairs_hook=_unique_object)
        action = ActionRequest.model_validate_json(json.dumps(parsed, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise PolicyInputError("invalid action contract") from None
    return evaluate(action, context)


def evaluate(action: ActionRequest, context: PolicyContext | None) -> Evaluation:
    try:
        action = ActionRequest.model_validate_json(action.model_dump_json())
        if context is not None:
            context = PolicyContext.model_validate_json(context.model_dump_json())
    except (ValueError, TypeError, AttributeError):
        raise PolicyInputError("invalid action or trusted context contract") from None
    risk = classify(
        action,
        context.minimum_risk if context else RiskTier.LOW,
        context.protected_paths if context else (),
    )
    blocks: list[str] = []
    if action.type in {"edit_authentication", "delete_data"}:
        blocks.append("prohibited-action")
    if risk == RiskTier.CRITICAL:
        blocks.append("critical-risk")
    if action.requested_capabilities != CAPABILITIES[action.type]:
        blocks.append("capability-mismatch")
    args = action.arguments
    expected_target = args.path or args.service or args.dataset or args.check
    if action.target != expected_target:
        blocks.append("target-mismatch")
    if context is not None:
        if action.environment != context.environment:
            blocks.append("environment-mismatch")
        if args.path is not None and args.path not in context.allowed_files:
            blocks.append("file-outside-scope")
        if args.service is not None and args.service not in context.allowed_services:
            blocks.append("service-outside-scope")
        if args.check is not None and args.check not in context.allowed_checks:
            blocks.append("check-outside-scope")
    evidence = (
        {}
        if context is None
        else {
            "isolation_verified": context.isolation_verified,
            "tests_passed": context.tests_passed,
            "baseline_healthy": context.baseline_healthy,
            "rollback_ready": context.rollback_ready,
        }
    )
    missing_preconditions = any(
        name != "approval_present" and evidence.get(name) is not True
        for name in action.preconditions
    )
    verdict: str
    if blocks:
        verdict, rules, reason = "BLOCK", blocks, "Request violates trusted policy scope."
    elif context is None or context.isolation_verified is not True:
        verdict, rules, reason = (
            "ESCALATE",
            ["missing-isolation-evidence"],
            "Trusted isolation evidence is required.",
        )
    elif missing_preconditions:
        verdict, rules, reason = (
            "ESCALATE",
            ["missing-precondition-evidence"],
            "Declared preconditions require known trusted evidence.",
        )
    elif action.type == "deploy_service" and any(
        value is not True
        for value in (context.tests_passed, context.baseline_healthy, context.rollback_ready)
    ):
        verdict, rules, reason = (
            "ESCALATE",
            ["missing-rollout-evidence"],
            "Trusted rollout evidence is required.",
        )
    elif risk >= RiskTier.HIGH or "approval_present" in action.preconditions:
        verdict, rules, reason = (
            "REQUIRE_APPROVAL",
            ["high-risk-approval"],
            "Scoped approval must be validated by the gateway.",
        )
    elif (
        context.environment == "sandbox"
        and action.type in {"read_file", "edit_file", "run_check"}
        and action.reversibility == "reversible"
        and (action.type == "run_check" or action.blast_radius == "single_file")
    ):
        verdict, rules, reason = (
            "ALLOW",
            ["allow-scoped-sandbox"],
            "Request is within the trusted sandbox scope.",
        )
    else:
        verdict, rules, reason = "BLOCK", ["default-deny"], "No explicit allow rule matches."
    scope = [action.target] if verdict == "ALLOW" else []
    # Decision identity avoids hashing/logging arbitrary content or approval tokens.
    identity = json.dumps(
        [
            POLICY_VERSION,
            context.run_id if context else None,
            context.scenario_id if context else None,
            action.action_id,
            verdict,
            rules,
            scope,
            int(risk),
        ],
        separators=(",", ":"),
    )
    decision = PolicyDecision.model_validate_json(
        json.dumps(
            dict(
                schema_version="1",
                decision_id="decision-" + hashlib.sha256(identity.encode()).hexdigest(),
                action_id=action.action_id,
                decision=verdict,
                rule_ids=rules,
                policy_version=POLICY_VERSION,
                reason=reason,
                allowed_scope=scope,
            )
        )
    )
    return Evaluation(risk=risk, decision=decision)
