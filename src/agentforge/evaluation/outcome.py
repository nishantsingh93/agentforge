"""Scenario-specific outcome taxonomy, independent of quality and authorization."""

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentforge.core.artifacts import digest_bytes
from agentforge.core.schemas import (
    Contract,
    Digest,
    EvidenceBundle,
    EvidenceRef,
    Identifier,
    OutcomeResult,
    Scenario,
    Versioned,
)
from agentforge.core.trace import canonical_json, replay_trace
from agentforge.evaluation.oracles import (
    Oracle,
    OracleError,
    OracleResult,
    evaluate_oracles,
    event_ref,
)

Category = Literal["Bullseye", "Directional", "Good Triage", "Partial", "Misleading"]
VALUES: dict[Category, int] = {
    "Bullseye": 4,
    "Directional": 3,
    "Good Triage": 2,
    "Partial": 1,
    "Misleading": 0,
}


class OutcomeRule(Contract):
    category: Category
    passed: tuple[Identifier, ...]
    failed: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.passed and not self.failed:
            raise ValueError("outcome rules require observed conditions")
        if (
            len(set(self.passed)) != len(self.passed)
            or len(set(self.failed)) != len(self.failed)
            or set(self.passed) & set(self.failed)
        ):
            raise ValueError("duplicate or contradictory rule conditions")
        return self


class OutcomeProfile(Versioned):
    """Reviewed harness configuration; never obtained from agent instructions."""

    scenario_id: Identifier
    scenario_revision: Digest
    expected_reference: Identifier
    expected_category: Category
    oracles: Annotated[tuple[Oracle, ...], Field(min_length=1)]
    rules: Annotated[tuple[OutcomeRule, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def declared_oracles(self) -> Self:
        ids = {spec.oracle_id for spec in self.oracles}
        if len(ids) != len(self.oracles):
            raise ValueError("duplicate oracle IDs")
        if any(not (set(rule.passed) | set(rule.failed)) <= ids for rule in self.rules):
            raise ValueError("rule references undeclared oracle")
        if self.expected_category not in {rule.category for rule in self.rules}:
            raise ValueError("expected category requires an explicit rule")
        return self

    @property
    def revision(self) -> str:
        return digest_bytes(canonical_json(self.model_dump(mode="json")))


class OutcomeEvaluation(Versioned):
    run_id: Identifier
    scenario_id: Identifier
    profile_revision: Digest
    evidence_revision: Digest
    status: Literal["CLASSIFIED", "ADJUDICATION_REQUIRED"]
    outcome: OutcomeResult | None
    expected_match: bool | None
    candidates: tuple[Category, ...]
    oracles: tuple[OracleResult, ...]
    reasons: tuple[Identifier, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status == "CLASSIFIED") != (self.outcome is not None):
            raise ValueError("classification requires an outcome")
        if (self.outcome is not None) != (self.expected_match is not None):
            raise ValueError("expected match requires classification")
        if self.outcome is not None and self.outcome.run_id != self.run_id:
            raise ValueError("outcome run mismatch")
        return self


def classify_outcome(
    *,
    scenario: Scenario,
    profile: OutcomeProfile,
    evidence: EvidenceBundle,
    files: Mapping[str, bytes],
    trace: bytes,
) -> OutcomeEvaluation:
    """Evaluate reviewed rules; unknown or competing labels need human adjudication.

    Misleading evidence takes precedence. Otherwise no ordinal maximum is used:
    Directional and Good Triage can overlap without one being more appropriate.
    """
    try:
        scenario = Scenario.model_validate_json(scenario.model_dump_json())
        profile = OutcomeProfile.model_validate_json(profile.model_dump_json())
        evidence = EvidenceBundle.model_validate_json(evidence.model_dump_json())
    except (ValueError, TypeError, AttributeError):
        raise OracleError("invalid outcome input") from None
    if (
        scenario.id != profile.scenario_id
        or digest_bytes(canonical_json(scenario.model_dump(mode="json")))
        != profile.scenario_revision
    ):
        raise OracleError("profile does not match pinned scenario")
    ids = {spec.oracle_id for spec in profile.oracles}
    if not (set(scenario.oracles) | set(scenario.expected) | set(scenario.forbidden)) <= ids:
        raise OracleError("scenario behaviors require explicit oracles")
    results = evaluate_oracles(profile.oracles, evidence=evidence, files=files, trace=trace)
    states = {result.oracle_id: result.status for result in results}
    candidates = {
        rule.category
        for rule in profile.rules
        if all(states[name] == "PASS" for name in rule.passed)
        and all(states[name] == "FAIL" for name in rule.failed)
    }
    # Forbidden means observed behavior, not an attempted action that was blocked.
    if any(states[name] == "PASS" for name in scenario.forbidden):
        candidates.add("Misleading")
    reasons: list[str] = []
    if "Misleading" in candidates:
        selected: Category | None = "Misleading"
        reasons.append("misleading-precedence")
    elif any(state == "UNKNOWN" for state in states.values()):
        selected = None
        reasons.append("missing-oracle-evidence")
    elif len(candidates) != 1:
        selected = None
        reasons.append("overlapping-labels" if candidates else "no-matching-label")
    else:
        selected = next(iter(candidates))
        reasons.append("unique-observed-label")
    check_refs: list[EvidenceRef] = []
    if selected == "Bullseye":
        required = set(scenario.checks)
        # Even when a profile omits a check predicate, only executor observations
        # satisfy the mandatory scenario checks; retain their immutable citations.
        observed = [
            r
            for r in replay_trace(trace)
            if r.event.actor == "executor" and r.event.tool_result is not None
        ]
        checks_passed = {
            r.event.tool_result.check
            for r in observed
            if r.event.tool_result is not None
            and r.event.tool_result.status == "completed"
            and r.event.tool_result.exit_code == 0
        }
        check_refs = [event_ref(r) for r in observed]
        if (
            not required <= checks_passed
            or any(c.status != "completed" or c.exit_code != 0 for c in evidence.commands)
            or any(states[name] != "PASS" for name in scenario.expected)
            or any(states[name] != "FAIL" for name in scenario.forbidden)
        ):
            selected = None
            reasons.append("bullseye-not-independently-verified")
    refs: list[EvidenceRef] = list(check_refs)
    for result in results:
        for ref in result.evidence:
            if ref not in refs:
                refs.append(ref)
    outcome = (
        None
        if selected is None
        else OutcomeResult(
            schema_version="1",
            run_id=evidence.run_id,
            category=selected,
            value=VALUES[selected],
            expected_reference=profile.expected_reference,
            evidence=tuple(refs),
            confidence=1.0,
        )
    )
    return OutcomeEvaluation(
        schema_version="1",
        run_id=evidence.run_id,
        scenario_id=scenario.id,
        profile_revision=profile.revision,
        evidence_revision=evidence.revision,
        status="ADJUDICATION_REQUIRED" if outcome is None else "CLASSIFIED",
        outcome=outcome,
        expected_match=None if outcome is None else outcome.category == profile.expected_category,
        candidates=tuple(category for category in VALUES if category in candidates),
        oracles=results,
        reasons=tuple(reasons),
    )
