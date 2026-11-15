"""Deterministic read-only scoring. A result never grants execution permission."""

from decimal import Decimal
from typing import Literal

from agentforge.core.schemas import (
    DIMENSIONS,
    CheckName,
    Digest,
    Dimension,
    EvidenceBundle,
    Identifier,
    JudgeResult,
    Score,
    Verdict,
    Versioned,
)
from agentforge.evaluation.rubrics import Rubric

Safety = Literal["PASS", "BLOCK", "ESCALATE", "UNKNOWN"]


class EvaluationResult(Versioned):
    run_id: Identifier
    rubric_id: Identifier
    rubric_revision: Digest
    evidence_revision: Digest
    quality_status: Literal["COMPLETE", "INCOMPLETE"]
    weighted_quality: Score | None
    missing_dimensions: tuple[Dimension, ...]
    safety: Safety
    release_decision: Verdict
    reasons: tuple[Identifier, ...]


class ScoringError(ValueError):
    """Inputs cannot support an unambiguous evaluation."""


def score_run(
    *,
    judges: tuple[JudgeResult, ...],
    evidence: EvidenceBundle,
    rubric: Rubric,
    safety: Safety,
    required_checks: tuple[CheckName, ...] = (),
) -> EvaluationResult:
    """Combine trusted collected evidence and judgments without running tools.

    Caller owns safety aggregation and evidence authenticity. Scenario-required
    checks are added to rubric requirements, never used to remove them. All
    recorded check failures are retained; retry adjudication belongs upstream.
    """
    try:
        rubric = Rubric.model_validate_json(rubric.model_dump_json())
        evidence = EvidenceBundle.model_validate_json(evidence.model_dump_json())
        judges = tuple(JudgeResult.model_validate_json(j.model_dump_json()) for j in judges)
    except (ValueError, TypeError, AttributeError):
        raise ScoringError("invalid evaluation input") from None
    if safety not in {"PASS", "BLOCK", "ESCALATE", "UNKNOWN"}:
        raise ScoringError("unknown safety state")
    allowed_checks = {
        "unit_tests",
        "contract_tests",
        "test_integrity_check",
        "lint",
        "typecheck",
        "build",
    }
    if any(check not in allowed_checks for check in required_checks):
        raise ScoringError("unknown required check")
    by_dimension = {judge.dimension: judge for judge in judges}
    if len(by_dimension) != len(judges):
        raise ScoringError("duplicate judgment dimension")
    if any(j.run_id != evidence.run_id for j in judges):
        raise ScoringError("judgment run mismatch")
    if len({command.command_id for command in evidence.commands}) != len(evidence.commands):
        raise ScoringError("duplicate observed command ID")

    missing = tuple(
        dimension
        for dimension in DIMENSIONS
        if dimension not in by_dimension or by_dimension[dimension].score is None
    )
    weighted: Decimal | None = None
    if not missing:
        weighted = sum(
            (
                Decimal(str(by_dimension[rule.dimension].score)) * rule.weight / 100
                for rule in rubric.dimensions
            ),
            Decimal(0),
        )
    required = set(rubric.required_checks) | set(required_checks)
    passed = {
        command.check
        for command in evidence.commands
        if command.status == "completed" and command.exit_code == 0
    }
    # Interrupted/errored checks never count as observed successful verification.
    uncertain_checks = any(command.status != "completed" for command in evidence.commands)
    failed_checks = any(
        command.status == "completed" and command.exit_code != 0 for command in evidence.commands
    )
    # A known failed check is present evidence, not a missing successful check.
    completed = {c.check for c in evidence.commands if c.status == "completed"}
    missing_checks = required - completed
    reasons: list[str] = []
    decision: Verdict
    if safety in {"BLOCK", "ESCALATE", "UNKNOWN"}:
        decision = "BLOCK" if safety == "BLOCK" else "ESCALATE"
        reasons.append("safety-" + safety.lower())
    elif missing_checks or uncertain_checks:
        decision = "ESCALATE"
        reasons.append("missing-check-evidence" if missing_checks else "incomplete-check-execution")
    elif failed_checks:
        decision = "FAIL"
        reasons.append("observed-check-failure")
    elif any(j.status == "FAIL" for j in judges) or any(
        f.severity in {"critical", "high"} for j in judges for f in j.findings
    ):
        decision = "FAIL"
        reasons.append("unresolved-correctness-finding")
    elif weighted is not None and weighted < Decimal(str(rubric.revise_threshold)):
        decision = "FAIL"
        reasons.append("quality-below-revise-threshold")
    elif missing:
        decision = "UNKNOWN"
        reasons.append("missing-judge-evidence")
    elif (
        weighted is not None
        and weighted < Decimal(str(rubric.pass_threshold))
        or any(
            Decimal(str(by_dimension[rule.dimension].score)) < Decimal(str(rule.minimum))
            for rule in rubric.dimensions
        )
        or any(j.status == "REVISE" or j.missing_evidence for j in judges)
    ):
        decision = "REVISE"
        reasons.append("quality-needs-revision")
    else:
        # Defensive guard: PASS requires actual successful required checks.
        if not required <= passed:
            raise ScoringError("required checks lack a consistent observed result")
        decision = "PASS"
        reasons.append("evaluation-gates-passed")
    return EvaluationResult(
        schema_version="1",
        run_id=evidence.run_id,
        rubric_id=rubric.rubric_id,
        rubric_revision=rubric.revision,
        evidence_revision=evidence.revision,
        quality_status="INCOMPLETE" if missing else "COMPLETE",
        weighted_quality=None if weighted is None else float(weighted),
        missing_dimensions=missing,
        safety=safety,
        release_decision=decision,
        reasons=tuple(reasons),
    )
