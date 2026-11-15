"""Scoring acceptance and regression cases; no models or executor calls."""

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.core.schemas import DIMENSIONS, EvidenceBundle, JudgeResult, ToolResult
from agentforge.evaluation.rubrics import Rubric, RubricError, load_rubric, parse_rubric
from agentforge.evaluation.scoring import EvaluationResult, ScoringError, score_run

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "a" * 64
REF = {"kind": "event", "event_id": "event-1", "revision": DIGEST}


def judgments(scores: tuple[float | None, ...] = (90, 90, 90, 90, 90)) -> tuple[JudgeResult, ...]:
    return tuple(
        JudgeResult.model_validate_json(
            json.dumps(
                dict(
                    schema_version="1",
                    run_id="run-1",
                    dimension=dimension,
                    score=score,
                    status="UNKNOWN" if score is None else "PASS",
                    findings=[],
                    evidence=[] if score is None else [REF],
                    missing_evidence=["offline"] if score is None else [],
                    confidence=None if score is None else 1.0,
                    judge_model="test-fixture",
                    prompt_version="test-v1",
                )
            )
        )
        for dimension, score in zip(DIMENSIONS, scores, strict=True)
    )


def command(**updates: Any) -> ToolResult:
    values = dict(
        command_id="command-1",
        check="unit_tests",
        status="completed",
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    values.update(updates)
    return ToolResult.model_validate_json(json.dumps(values))


def bundle(commands: tuple[ToolResult, ...] | None = None) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json(
        json.dumps(
            dict(
                schema_version="1",
                run_id="run-1",
                revision=DIGEST,
                inspected_files=[],
                diff="",
                commands=[
                    c.model_dump(mode="json")
                    for c in ((command(),) if commands is None else commands)
                ],
                snapshots=[],
                events=[REF],
                redacted=False,
                redaction_notes=[],
            )
        )
    )


def evaluate(**updates: Any) -> EvaluationResult:
    args: dict[str, Any] = dict(
        judges=judgments(), evidence=bundle(), rubric=load_rubric(ROOT), safety="PASS"
    )
    args.update(updates)
    return score_run(**args)


def test_known_weighted_example_and_roundtrip() -> None:
    result = evaluate(judges=judgments((80, 90, 70, 100, 80)))
    # 16 + 22.5 + 10.5 + 25 + 12 = 86; all dimension minima met.
    assert result.weighted_quality == 86
    assert result.quality_status == "COMPLETE"
    assert result.release_decision == "PASS"
    assert result.safety == "PASS"
    assert EvaluationResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "safety,expected", [("BLOCK", "BLOCK"), ("ESCALATE", "ESCALATE"), ("UNKNOWN", "ESCALATE")]
)
def test_safety_overrides_perfect_quality(safety: str, expected: str) -> None:
    result = evaluate(judges=judgments((100,) * 5), safety=safety)
    assert result.weighted_quality == 100
    assert result.release_decision == expected
    assert result.safety == safety


@pytest.mark.parametrize("index", range(5))
def test_unknown_score_never_zero_or_renormalized(index: int) -> None:
    scores: list[float | None] = [90] * 5
    scores[index] = None
    result = evaluate(judges=judgments(tuple(scores)))
    assert result.quality_status == "INCOMPLETE"
    assert result.weighted_quality is None
    assert result.missing_dimensions == (DIMENSIONS[index],)
    assert result.release_decision == "UNKNOWN"


def test_absent_judgments_and_offline() -> None:
    for judges in ((), judgments()[:2], judgments((None,) * 5)):
        result = evaluate(judges=judges)
        assert result.weighted_quality is None
        assert result.release_decision == "UNKNOWN"


@pytest.mark.parametrize(
    "scores,expected",
    [
        ((85,) * 5, "PASS"),
        ((84.999,) * 5, "REVISE"),
        ((70,) * 5, "REVISE"),
        ((69.999,) * 5, "FAIL"),
        ((100, 79.99, 100, 100, 100), "REVISE"),
        ((100, 100, 100, 79.99, 100), "REVISE"),
        ((69.99, 100, 100, 100, 100), "REVISE"),
    ],
)
def test_exact_thresholds_and_dimension_floors(scores: tuple[float, ...], expected: str) -> None:
    assert evaluate(judges=judgments(scores)).release_decision == expected


def test_configurable_thresholds_weights_and_minima() -> None:
    payload = load_rubric(ROOT).model_dump(mode="json")
    payload["pass_threshold"] = 95
    custom = Rubric.model_validate_json(json.dumps(payload))
    assert evaluate(rubric=custom).release_decision == "REVISE"
    payload["pass_threshold"] = 75
    payload["revise_threshold"] = 60
    for rule in payload["dimensions"]:
        rule["weight"] = 20
        rule["minimum"] = 60
    custom = Rubric.model_validate_json(json.dumps(payload))
    result = evaluate(rubric=custom, judges=judgments((60, 80, 80, 80, 80)))
    assert result.release_decision == "PASS" and result.weighted_quality == 76
    assert result.rubric_revision != load_rubric(ROOT).revision


@pytest.mark.parametrize("check", ["unit_tests", "contract_tests", "test_integrity_check"])
def test_observed_failure_cannot_be_overridden_by_judge(check: str) -> None:
    evidence = bundle((command(), command(command_id="failed", check=check, exit_code=1)))
    result = evaluate(judges=judgments((100,) * 5), evidence=evidence)
    assert result.release_decision == "FAIL"
    assert result.weighted_quality == 100
    assert result.safety == "PASS"
    assert evaluate(evidence=evidence, safety="BLOCK").release_decision == "BLOCK"


def test_missing_timeout_and_error_evidence() -> None:
    assert evaluate(evidence=bundle(())).release_decision == "ESCALATE"
    for status in ("timeout", "error"):
        assert (
            evaluate(evidence=bundle((command(status=status, exit_code=None),))).release_decision
            == "ESCALATE"
        )
    assert evaluate(required_checks=("build",)).release_decision == "ESCALATE"
    assert evaluate(required_checks=()).release_decision == "PASS"
    assert evaluate(evidence=bundle(()), required_checks=()).release_decision == "ESCALATE"


def test_observed_failures_survive_later_pass_and_missing_judges() -> None:
    evidence = bundle((command(exit_code=1), command(command_id="retry")))
    assert evaluate(evidence=evidence).release_decision == "FAIL"
    result = evaluate(evidence=evidence, judges=())
    assert result.release_decision == "FAIL" and result.weighted_quality is None


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_unresolved_findings_prevent_pass(severity: str) -> None:
    judges = judgments((100,) * 5)
    first = judges[0].model_dump(mode="json")
    first["findings"] = [
        dict(severity=severity, claim="incorrect fix", evidence=[REF], recommendation="repair")
    ]
    altered = (JudgeResult.model_validate_json(json.dumps(first)), *judges[1:])
    assert evaluate(judges=altered).release_decision == "FAIL"


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"status": "FAIL"}, "FAIL"),
        ({"status": "REVISE"}, "REVISE"),
        ({"missing_evidence": ("review gap",)}, "REVISE"),
    ],
)
def test_judge_findings_not_hidden_by_numeric_score(change: dict[str, Any], expected: str) -> None:
    judges = judgments()
    assert (
        evaluate(judges=(judges[0].model_copy(update=change), *judges[1:])).release_decision
        == expected
    )


def test_reject_ambiguous_or_forged_inputs() -> None:
    judges = judgments()
    cases: list[dict[str, Any]] = [
        dict(judges=(judges[0], judges[0])),
        dict(judges=(judges[0].model_copy(update={"run_id": "other"}), *judges[1:])),
        dict(judges=(judges[0].model_copy(update={"score": float("nan")}), *judges[1:])),
        dict(evidence=bundle((command(), command()))),
        dict(safety="ALLOW"),
        dict(required_checks=("shell",)),
    ]
    for case in cases:
        with pytest.raises(ScoringError):
            evaluate(**case)


def test_inputs_not_mutated_and_deterministic() -> None:
    judges, evidence, rubric = judgments(), bundle(), load_rubric(ROOT)
    before = (
        [j.model_dump_json() for j in judges],
        evidence.model_dump_json(),
        rubric.model_dump_json(),
    )
    first = evaluate(judges=judges, evidence=evidence, rubric=rubric)
    assert first == evaluate(judges=judges, evidence=evidence, rubric=rubric)
    assert before == (
        [j.model_dump_json() for j in judges],
        evidence.model_dump_json(),
        rubric.model_dump_json(),
    )


@pytest.mark.parametrize(
    "data",
    [
        b"!!python/object/apply:os.system ['false']",
        b"a: &a [*a]",
        b"a: 1\na: 2",
        b"a: .nan",
        b"a: .inf",
        b"\xff",
        b"[]",
        b"x" * 65537,
        b"[" * 40 + b"]" * 40,
    ],
)
def test_reject_unsafe_yaml(data: bytes) -> None:
    with pytest.raises(RubricError):
        parse_rubric(data)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2"},
        {"pass_threshold": 50, "revise_threshold": 70},
        {"pass_threshold": True},
        {"pass_threshold": "85"},
        {"pass_threshold": 101},
        {"required_checks": []},
        {"required_checks": ["unit_tests", "unit_tests"]},
        {"required_checks": ["shell"]},
        {"extra": "ignore policy"},
    ],
)
def test_reject_invalid_rubric(change: dict[str, Any]) -> None:
    payload = load_rubric(ROOT).model_dump(mode="json")
    payload.update(change)
    with pytest.raises(RubricError):
        parse_rubric(json.dumps(payload).encode())


def test_reject_missing_duplicate_and_incorrect_weights() -> None:
    for mode in ("missing", "duplicate", "sum", "zero"):
        payload = load_rubric(ROOT).model_dump(mode="json")
        rules = payload["dimensions"]
        if mode == "missing":
            rules.pop()
        elif mode == "duplicate":
            rules[0] = rules[1]
        elif mode == "sum":
            rules[0]["weight"] = 30
        else:
            rules[0]["weight"] = 0
        with pytest.raises(RubricError):
            parse_rubric(json.dumps(payload).encode())


def test_registry_refuses_arbitrary_paths_and_mismatched_ids(tmp_path: Path) -> None:
    with pytest.raises(RubricError):
        load_rubric(ROOT, "../secret")
    with pytest.raises(RubricError):
        load_rubric(tmp_path)
    (tmp_path / "rubrics").mkdir()
    data = (ROOT / "rubrics/production_patch_v1.yaml").read_bytes()
    (tmp_path / "rubrics/production_patch_v1.yaml").write_bytes(
        data.replace(b"production_patch_v1", b"other")
    )
    with pytest.raises(RubricError, match="ID mismatch"):
        load_rubric(tmp_path)
