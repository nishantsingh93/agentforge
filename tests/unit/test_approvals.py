"""Synthetic grants bound to exact actions; no real credentials."""

import pytest
from test_policy import action

from agentforge.guardrails.approvals import ApprovalError, ApprovalRegistry
from agentforge.guardrails.policy import POLICY_VERSION


def test_valid_grant_consumed_once_and_exact_expiry() -> None:
    now = [100.0]
    registry = ApprovalRegistry(lambda: now[0])
    request = action("edit_file", dry_run=False)
    token = registry.issue(request, "run-1", POLICY_VERSION, ttl_seconds=5)
    request = request.model_copy(update={"approval_token": token})
    registry.validate(request, "run-1", POLICY_VERSION)
    registry.validate(request, "run-1", POLICY_VERSION, consume=True)
    with pytest.raises(ApprovalError):
        registry.validate(request, "run-1", POLICY_VERSION)
    token = registry.issue(request, "run-1", POLICY_VERSION, ttl_seconds=5)
    now[0] = 105.0
    with pytest.raises(ApprovalError):
        registry.validate(
            request.model_copy(update={"approval_token": token}), "run-1", POLICY_VERSION
        )


@pytest.mark.parametrize(
    "change", ["run", "version", "target", "content", "idempotency", "dry_run", "missing", "forged"]
)
def test_wrong_grants_never_validate(change: str) -> None:
    registry = ApprovalRegistry(lambda: 100.0)
    request = action("edit_file", dry_run=False)
    token = registry.issue(request, "run-1", POLICY_VERSION)
    request = request.model_copy(update={"approval_token": token})
    if change == "target":
        request = request.model_copy(update={"target": "other.py"})
    elif change == "content":
        request = request.model_copy(
            update={"arguments": request.arguments.model_copy(update={"content": "different"})}
        )
    elif change == "idempotency":
        request = request.model_copy(update={"idempotency_key": "other"})
    elif change == "dry_run":
        request = request.model_copy(update={"dry_run": True})
    elif change in {"missing", "forged"}:
        request = request.model_copy(
            update={"approval_token": None if change == "missing" else "fake"}
        )
    with pytest.raises(ApprovalError):
        registry.validate(
            request,
            "other" if change == "run" else "run-1",
            "other" if change == "version" else POLICY_VERSION,
        )


@pytest.mark.parametrize("ttl", [0.0, -1.0, float("nan"), float("inf"), 3601.0])
def test_invalid_lifetime_rejected(ttl: float) -> None:
    with pytest.raises(ApprovalError):
        ApprovalRegistry().issue(action(), "run-1", POLICY_VERSION, ttl_seconds=ttl)


def test_clock_regression_and_nonfinite_clock_fail_closed() -> None:
    now = [100.0]
    registry = ApprovalRegistry(lambda: now[0])
    request = action()
    token = registry.issue(request, "run-1", POLICY_VERSION)
    request = request.model_copy(update={"approval_token": token})
    for value in (99.0, float("nan"), float("inf")):
        now[0] = value
        with pytest.raises(ApprovalError):
            registry.validate(request, "run-1", POLICY_VERSION)


def test_invalid_grant_request_error_hides_raw_input() -> None:
    request = action().model_copy(update={"target": "", "approval_token": "raw-secret with spaces"})
    with pytest.raises(ApprovalError) as error:
        ApprovalRegistry().issue(request, "run-1", POLICY_VERSION)
    assert "raw-secret" not in str(error.value) and error.value.__suppress_context__
