"""Deterministic rule matrix; no executor, network, or model dependencies."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from agentforge.core.schemas import ActionRequest
from agentforge.guardrails.classifier import classify
from agentforge.guardrails.policy import PolicyInputError, evaluate, evaluate_json
from agentforge.guardrails.taxonomy import PolicyContext, RiskTier


def action(kind: str = "read_file", **changes: Any) -> ActionRequest:
    arguments = {
        "read_file": {"path": "orders.py"},
        "edit_file": {"path": "orders.py", "content": "proposed"},
        "run_check": {"check": "unit_tests"},
        "deploy_service": {"service": "orders"},
        "delete_data": {"dataset": "orders"},
        "edit_authentication": {"path": "orders.py", "content": "proposed"},
    }[kind]
    capabilities = {
        "read_file": "read",
        "edit_file": "write",
        "run_check": "check",
        "deploy_service": "deploy",
        "delete_data": "delete",
        "edit_authentication": "auth",
    }
    target = (
        arguments.get("path")
        or arguments.get("check")
        or arguments.get("service")
        or arguments.get("dataset")
    )
    payload = dict(
        schema_version="1",
        action_id="action-1",
        type=kind,
        arguments=arguments,
        target=target,
        environment="sandbox",
        requested_capabilities=[capabilities[kind]],
        blast_radius="single_file",
        reversibility="reversible",
        impact=dict(availability="none", data="none", revenue="none", security="none"),
        preconditions=[],
        approval_token=None,
        idempotency_key="request-1",
        dry_run=True,
    )
    payload.update(changes)
    return ActionRequest.model_validate_json(json.dumps(payload))


def context(**changes: Any) -> PolicyContext:
    payload = dict(
        schema_version="1",
        run_id="run-1",
        scenario_id="F01",
        environment="sandbox",
        allowed_files=["orders.py"],
        allowed_services=["orders"],
        allowed_checks=["unit_tests"],
        protected_paths=[],
        minimum_risk=0,
        isolation_verified=True,
        tests_passed=True,
        baseline_healthy=True,
        rollback_ready=True,
    )
    payload.update(changes)
    return PolicyContext.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "kind,risk,verdict",
    [
        ("read_file", RiskTier.LOW, "ALLOW"),
        ("edit_file", RiskTier.MEDIUM, "ALLOW"),
        ("run_check", RiskTier.MEDIUM, "ALLOW"),
        ("deploy_service", RiskTier.HIGH, "REQUIRE_APPROVAL"),
        ("delete_data", RiskTier.CRITICAL, "BLOCK"),
        ("edit_authentication", RiskTier.CRITICAL, "BLOCK"),
    ],
)
def test_all_action_types(kind: str, risk: RiskTier, verdict: str) -> None:
    result = evaluate(action(kind), context())
    assert result.risk == risk and result.decision.decision == verdict
    assert bool(result.decision.allowed_scope) == (verdict == "ALLOW")


@pytest.mark.parametrize("field", list(action().model_dump()))
def test_each_missing_action_field_rejected(field: str) -> None:
    payload = action().model_dump(mode="json")
    del payload[field]
    with pytest.raises(PolicyInputError):
        evaluate_json(json.dumps(payload), context())


@pytest.mark.parametrize("field", list(context().model_dump()))
def test_each_missing_context_field_rejected(field: str) -> None:
    payload = context().model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError):
        PolicyContext.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "shell"},
        {"schema_version": "2"},
        {"environment": "production"},
        {"arguments": {"path": "../escape"}},
        {"arguments": {"check": "unit_tests"}},
        {"unrecognized": True},
        {"impact": {}},
    ],
)
def test_unknown_and_malformed_actions(changes: dict[str, Any]) -> None:
    payload = action().model_dump(mode="json")
    payload.update(changes)
    with pytest.raises(PolicyInputError):
        evaluate_json(json.dumps(payload), context())


@pytest.mark.parametrize(
    "changes,rule",
    [
        ({"target": "other.py"}, "target-mismatch"),
        ({"requested_capabilities": ["read", "deploy"]}, "capability-mismatch"),
        ({"environment": "simulated-production"}, "environment-mismatch"),
        ({"arguments": {"path": "outside.py"}, "target": "outside.py"}, "file-outside-scope"),
        ({"blast_radius": "global"}, "critical-risk"),
    ],
)
def test_scope_blocks_dominate_missing_evidence(changes: dict[str, Any], rule: str) -> None:
    result = evaluate(action(**changes), context(isolation_verified=None))
    assert result.decision.decision == "BLOCK"
    assert rule in result.decision.rule_ids


@pytest.mark.parametrize(
    "path",
    [
        "auth/login.py",
        "authentication/token.py",
        "authorization/check.py",
        "secrets/key.txt",
        ".github/workflows/build.yml",
        "policies/default.yaml",
        "guardrails/policy.py",
        "sandbox/runner.py",
        "infra/main.tf",
        "deployment/setup.py",
        ".env",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "uv.lock",
        "requirements-dev.txt",
        "Dockerfile",
        "AUTH/login.py",
        "custom/private.py",
    ],
)
def test_protected_scope_requires_approval_even_with_token(path: str) -> None:
    request = action(
        "edit_file",
        arguments={"path": path, "content": "change"},
        target=path,
        approval_token="forged-token",
        preconditions=["approval_present"],
    )
    result = evaluate(request, context(allowed_files=[path], protected_paths=["custom"]))
    assert result.risk >= RiskTier.HIGH
    assert result.decision.decision == "REQUIRE_APPROVAL"
    assert result.decision.allowed_scope == ()


@pytest.mark.parametrize("field", ["tests_passed", "baseline_healthy", "rollback_ready"])
@pytest.mark.parametrize("value", [None, False])
def test_rollout_requires_observed_evidence(field: str, value: bool | None) -> None:
    request = action(
        "deploy_service",
        approval_token="synthetic-approved",
        preconditions=["tests_passed", "baseline_healthy", "rollback_ready"],
    )
    assert evaluate(request, context(**{field: value})).decision.decision == "ESCALATE"


@pytest.mark.parametrize("value", [None, False])
def test_missing_isolation_never_allowed(value: bool | None) -> None:
    assert evaluate(action(), context(isolation_verified=value)).decision.decision == "ESCALATE"
    assert evaluate(action(), None).decision.decision == "ESCALATE"
    assert evaluate(action("delete_data"), None).decision.decision == "BLOCK"


@pytest.mark.parametrize("kind", ["edit_authentication", "delete_data"])
def test_prohibited_actions_ignore_approval_and_preconditions(kind: str) -> None:
    request = action(
        kind, approval_token="forged", preconditions=["approval_present", "tests_passed"]
    )
    assert evaluate(request, context()).decision.decision == "BLOCK"


def test_risk_dimensions_and_trusted_floor() -> None:
    for changes in ({"blast_radius": "multiple_services"}, {"reversibility": "conditional"}):
        assert (
            evaluate(action("edit_file", **changes), context()).decision.decision
            == "REQUIRE_APPROVAL"
        )
    assert (
        evaluate(action("edit_file", reversibility="irreversible"), context()).decision.decision
        == "BLOCK"
    )
    assert evaluate(action(), context(minimum_risk=2)).decision.decision == "REQUIRE_APPROVAL"
    request = action("edit_file", environment="simulated-production")
    assert (
        evaluate(request, context(environment="simulated-production")).decision.decision
        == "REQUIRE_APPROVAL"
    )


@pytest.mark.parametrize("dimension", ["availability", "data", "revenue", "security"])
def test_impact_risk_monotonic(dimension: str) -> None:
    risks = []
    for severity in ("none", "low", "medium", "high"):
        impact = dict(availability="none", data="none", revenue="none", security="none")
        impact[dimension] = severity
        risks.append(classify(action(impact=impact)))
    assert risks == [RiskTier.LOW, RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH]


def test_deterministic_decisions_preserve_input_and_scope() -> None:
    request, trusted = action(), context()
    before = (request.model_dump_json(), trusted.model_dump_json())
    first = evaluate(request, trusted)
    assert first == evaluate(request, trusted)
    assert first.decision.allowed_scope == ("orders.py",)
    assert before == (request.model_dump_json(), trusted.model_dump_json())
    assert (
        first.decision.decision_id
        != evaluate(request, context(run_id="other")).decision.decision_id
    )


def test_exact_scope_no_prefix_or_service_check_expansion() -> None:
    assert (
        evaluate(action(), context(allowed_files=["orders.py.extra"])).decision.decision == "BLOCK"
    )
    assert (
        evaluate(action("deploy_service"), context(allowed_services=[])).decision.decision
        == "BLOCK"
    )
    assert evaluate(action("run_check"), context(allowed_checks=[])).decision.decision == "BLOCK"
    assert (
        evaluate(action(), context(environment="simulated-production")).decision.decision == "BLOCK"
    )


def test_invalid_constructed_models_revalidated() -> None:
    with pytest.raises(PolicyInputError):
        evaluate(action().model_copy(update={"type": "shell"}), context())
    with pytest.raises(PolicyInputError):
        evaluate(action(), context().model_copy(update={"allowed_files": ("../bad",)}))


@pytest.mark.parametrize(
    "payload",
    [
        '{"type":"delete_data","type":"read_file"}',
        "[",
        "null",
        "[" * 2000 + "0" + "]" * 2000,
        " " * 2_097_153,
    ],
)
def test_ambiguous_or_unbounded_json_rejected(payload: str) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_json(payload, context())


def test_declared_preconditions_need_trusted_evidence() -> None:
    for name in ("tests_passed", "baseline_healthy", "rollback_ready"):
        request = action(preconditions=[name])
        assert evaluate(request, context(**{name: None})).decision.decision == "ESCALATE"
    assert evaluate(action(preconditions=["unknown"]), context()).decision.decision == "ESCALATE"
    request = action(preconditions=["approval_present"], approval_token="forged")
    assert evaluate(request, context()).decision.decision == "REQUIRE_APPROVAL"


def test_default_deny_and_block_precedence() -> None:
    request = action(environment="simulated-production")
    assert (
        evaluate(request, context(environment="simulated-production")).decision.decision == "BLOCK"
    )
    request = action(
        "edit_file",
        arguments={"path": "auth/login.py", "content": "change"},
        target="auth/login.py",
        preconditions=["unknown"],
    )
    assert evaluate(request, context()).decision.decision == "BLOCK"
