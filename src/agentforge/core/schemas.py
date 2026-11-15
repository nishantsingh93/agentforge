"""Version-one wire contracts. Validation never authorizes or executes actions."""

import json
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Text = Annotated[str, Field(min_length=1, max_length=16384)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
Digest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
Count = Annotated[int, Field(ge=0)]
Score = Annotated[float, Field(ge=0, le=100)]
Confidence = Annotated[float, Field(ge=0, le=1)]
Dimension = Literal[
    "repository_awareness",
    "architecture_compliance",
    "planning_quality",
    "patch_correctness",
    "verification_quality",
]
DIMENSIONS: tuple[Dimension, ...] = (
    "repository_awareness",
    "architecture_compliance",
    "planning_quality",
    "patch_correctness",
    "verification_quality",
)
ActionType = Literal[
    "read_file", "edit_file", "run_check", "deploy_service", "delete_data", "edit_authentication"
]
Environment = Literal["sandbox", "simulated-production"]
CheckName = Literal[
    "unit_tests", "contract_tests", "test_integrity_check", "lint", "typecheck", "build"
]
Verdict = Literal["PASS", "REVISE", "FAIL", "BLOCK", "ESCALATE", "UNKNOWN"]


def relative_path(value: str) -> str:
    """Reject ambiguous or escaping wire paths; filesystem checks are separate."""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or "\\" in value
        or ":" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("expected a canonical relative POSIX path")
    return value


class Contract(BaseModel):
    """Strict model with frozen fields; nested JSON is not deeply immutable."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


class Versioned(Contract):
    schema_version: Literal["1"]


class FileRef(Contract):
    kind: Literal["file"]
    path: Text
    revision: Digest
    start_line: Annotated[int, Field(ge=1)]
    end_line: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def valid_location(self) -> Self:
        relative_path(self.path)
        if self.end_line < self.start_line:
            raise ValueError("end_line precedes start_line")
        return self


class EventRef(Contract):
    kind: Literal["event"]
    event_id: Identifier
    revision: Digest


EvidenceRef = Annotated[FileRef | EventRef, Field(discriminator="kind")]


class Fault(Contract):
    type: Literal["fixture_patch", "mock", "fault_proxy"]
    ref: Text

    @model_validator(mode="after")
    def valid_ref(self) -> Self:
        relative_path(self.ref)
        return self


class Scenario(Versioned):
    id: Annotated[str, Field(pattern=r"^F[0-9]{2,}$")]
    version: Annotated[int, Field(ge=1)]
    name: Identifier
    category: Literal[
        "correctness", "architecture", "safety", "operations", "triage", "tool_integrity"
    ]
    difficulty: Literal["easy", "medium", "hard"]
    fixture: Annotated[str, Field(pattern=r"^[a-z0-9-]+@sha256:[a-f0-9]{64}$")]
    agent_task: Text
    fault: Fault
    policy: Identifier
    expected: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    forbidden: tuple[Identifier, ...]
    oracles: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    checks: Annotated[tuple[CheckName, ...], Field(min_length=1)]
    rubric: Identifier

    @model_validator(mode="after")
    def unique_expectations(self) -> Self:
        for values in (self.expected, self.forbidden, self.oracles, self.checks):
            if len(values) != len(set(values)):
                raise ValueError("duplicate scenario declarations")
        if set(self.expected) & set(self.forbidden):
            raise ValueError("expected and forbidden behaviors overlap")
        return self


class Impact(Contract):
    availability: Literal["none", "low", "medium", "high"]
    data: Literal["none", "low", "medium", "high"]
    revenue: Literal["none", "low", "medium", "high"]
    security: Literal["none", "low", "medium", "high"]


class Arguments(Contract):
    path: Text | None = None
    content: Annotated[str, Field(max_length=1_000_000)] | None = None
    check: CheckName | None = None
    service: Identifier | None = None
    dataset: Identifier | None = None


class ActionRequest(Versioned):
    action_id: Identifier
    type: ActionType
    arguments: Arguments
    target: Text
    environment: Environment
    requested_capabilities: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    blast_radius: Literal["single_file", "single_service", "multiple_services", "global"]
    reversibility: Literal["reversible", "conditional", "irreversible"]
    impact: Impact
    preconditions: tuple[Identifier, ...]
    approval_token: Identifier | None
    idempotency_key: Identifier
    dry_run: bool

    @model_validator(mode="after")
    def matching_arguments(self) -> Self:
        required = {
            "read_file": {"path"},
            "edit_file": {"path", "content"},
            "run_check": {"check"},
            "deploy_service": {"service"},
            "delete_data": {"dataset"},
            "edit_authentication": {"path", "content"},
        }[self.type]
        present = {key for key, value in self.arguments.model_dump().items() if value is not None}
        if present != required:
            raise ValueError("arguments do not match action type")
        if self.arguments.path is not None:
            relative_path(self.arguments.path)
        return self


class PolicyDecision(Versioned):
    decision_id: Identifier
    action_id: Identifier
    decision: Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL", "ESCALATE"]
    rule_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    policy_version: Identifier
    reason: Text
    allowed_scope: tuple[Text, ...]

    @model_validator(mode="after")
    def consistent_scope(self) -> Self:
        if (self.decision == "ALLOW") != bool(self.allowed_scope):
            raise ValueError("only ALLOW decisions must carry a nonempty scope")
        return self


class ToolResult(Contract):
    command_id: Identifier
    check: CheckName | None
    status: Literal["completed", "timeout", "error"]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def observed_exit(self) -> Self:
        if self.status == "completed" and self.exit_code is None:
            raise ValueError("completed commands require observed exit codes")
        return self


class TraceEvent(Versioned):
    event_id: Identifier
    run_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    timestamp: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")]
    actor: Literal["agent", "gateway", "executor", "oracle", "judge", "runner"]
    parent_id: Identifier | None
    action: ActionRequest | None
    policy_decision: PolicyDecision | None
    tool_result: ToolResult | None
    evidence: tuple[EvidenceRef, ...]
    claim: Text | None

    @model_validator(mode="after")
    def consistent_event(self) -> Self:
        datetime.fromisoformat(self.timestamp)
        if self.parent_id == self.event_id:
            raise ValueError("an event cannot parent itself")
        if self.actor == "agent" and self.tool_result is not None:
            raise ValueError("agent claims cannot be recorded as observed tool results")
        if self.action is not None and self.policy_decision is not None:
            if self.action.action_id != self.policy_decision.action_id:
                raise ValueError("policy decision references a different action")
        return self


class StateSnapshot(Contract):
    snapshot_id: Identifier
    revision: Digest
    state: dict[str, JsonValue]


class EvidenceBundle(Versioned):
    run_id: Identifier
    revision: Digest
    inspected_files: tuple[FileRef, ...]
    diff: str
    commands: tuple[ToolResult, ...]
    snapshots: tuple[StateSnapshot, ...]
    events: tuple[EventRef, ...]
    redacted: bool
    redaction_notes: tuple[Text, ...]


class Finding(Contract):
    severity: Literal["info", "low", "medium", "high", "critical"]
    claim: Text
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]
    recommendation: Text


class JudgeResult(Versioned):
    run_id: Identifier
    dimension: Dimension
    score: Score | None
    status: Literal["PASS", "REVISE", "FAIL", "UNKNOWN"]
    findings: tuple[Finding, ...]
    evidence: tuple[EvidenceRef, ...]
    missing_evidence: tuple[Text, ...]
    confidence: Confidence | None
    judge_model: Text
    prompt_version: Identifier

    @model_validator(mode="after")
    def evidence_not_invention(self) -> Self:
        if self.status == "UNKNOWN":
            if self.score is not None or self.confidence is not None or not self.missing_evidence:
                raise ValueError(
                    "UNKNOWN requires missing evidence and no invented score/confidence"
                )
        elif self.score is None or self.confidence is None or not self.evidence:
            raise ValueError("known judgments require score, confidence, and evidence")
        return self


class OutcomeResult(Versioned):
    run_id: Identifier
    category: Literal["Bullseye", "Directional", "Good Triage", "Partial", "Misleading"]
    value: Annotated[int, Field(ge=0, le=4)]
    expected_reference: Identifier
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]
    confidence: Confidence

    @model_validator(mode="after")
    def category_value(self) -> Self:
        values = {"Bullseye": 4, "Directional": 3, "Good Triage": 2, "Partial": 1, "Misleading": 0}
        if self.value != values[self.category]:
            raise ValueError("outcome value does not match category")
        return self


class Metric(Contract):
    numerator: Count
    denominator: Count

    @model_validator(mode="after")
    def valid_counts(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("numerator exceeds denominator")
        return self


class RunReport(Versioned):
    run_id: Identifier
    scenario_id: Annotated[str, Field(pattern=r"^F[0-9]{2,}$")]
    quality_status: Literal["COMPLETE", "INCOMPLETE"]
    weighted_quality: Score | None
    judges: Annotated[tuple[JudgeResult, ...], Field(min_length=5, max_length=5)]
    safety: Literal["PASS", "BLOCK", "ESCALATE", "UNKNOWN"]
    outcome: OutcomeResult | None
    release_decision: Verdict
    metrics: dict[Identifier, Metric]
    config: dict[str, JsonValue]
    audit_artifacts: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def consistent_report(self) -> Self:
        if {judge.dimension for judge in self.judges} != set(DIMENSIONS):
            raise ValueError("report must contain each rubric dimension exactly once")
        if any(judge.run_id != self.run_id for judge in self.judges):
            raise ValueError("judge run_id mismatch")
        if self.outcome is not None and self.outcome.run_id != self.run_id:
            raise ValueError("outcome run_id mismatch")
        complete = all(judge.score is not None for judge in self.judges)
        if (self.quality_status == "COMPLETE") != complete:
            raise ValueError("quality status contradicts judge evidence")
        if (self.weighted_quality is not None) != complete:
            raise ValueError("aggregate score requires complete evidence")
        if self.release_decision == "PASS" and (not complete or self.safety != "PASS"):
            raise ValueError("PASS cannot accompany missing evidence or nonpassing safety")
        return self


MODELS: tuple[type[Versioned], ...] = (
    Scenario,
    ActionRequest,
    PolicyDecision,
    TraceEvent,
    EvidenceBundle,
    JudgeResult,
    OutcomeResult,
    RunReport,
)


def export_json_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schema documents without writing files or invoking tools."""
    return {model.__name__: model.model_json_schema() for model in MODELS}


if __name__ == "__main__":
    print(json.dumps(export_json_schemas(), indent=2, sort_keys=True))
