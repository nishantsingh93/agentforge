"""Benchmark fixtures test measurement, not real model intelligence or human expertise."""

import json
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentforge.benchmarks.data import (
    Case,
    Label,
    Review,
    load_cases,
    load_jsonl,
    request_for,
    request_revision,
    validate_labels,
)
from agentforge.benchmarks.harness import Prediction, predict
from agentforge.benchmarks.metrics import kappa, rate
from agentforge.benchmarks.scoring import BenchmarkReport, score
from agentforge.cli import app
from agentforge.evaluation.rubrics import load_rubric
from agentforge.providers.base import JudgeRequest, ProviderResponse
from agentforge.providers.offline import OfflineProvider

ROOT = Path(__file__).resolve().parents[2]
CASES = load_cases(ROOT / "benchmarks/cases.jsonl")
LABELS = load_jsonl(ROOT / "benchmarks/labels.jsonl", Label)
RUBRIC = load_rubric(ROOT)


def subset(statuses: list[str]) -> tuple[tuple[Case, ...], tuple[Label, ...]]:
    chosen = []
    for status in statuses:
        chosen.append(
            next(label for label in LABELS if label.status == status and label not in chosen)
        )
    by_id = {c.case_id: c for c in CASES}
    return tuple(by_id[label.case_id] for label in chosen), tuple(chosen)


class FixtureProvider:
    """Predeclared test responses; NEVER used as benchmark model predictions."""

    def __init__(self, statuses: list[str], bad_citation: bool = False) -> None:
        self.statuses = iter(statuses)
        self.bad_citation = bad_citation
        self.requests: list[JudgeRequest] = []

    def complete(self, request: JudgeRequest) -> ProviderResponse:
        self.requests.append(request)
        status = next(self.statuses)
        ref = json.loads(request.evidence_json)["evidence"]["bundle"]["inspected_files"][0]
        if self.bad_citation:
            ref["revision"] = "sha256:" + "0" * 64
        output = dict(
            schema_version="1",
            run_id=request.run_id,
            dimension=request.dimension,
            score={"PASS": 95.0, "REVISE": 75.0, "FAIL": 30.0}.get(status),
            status=status,
            findings=[],
            evidence=[] if status == "UNKNOWN" else [ref],
            missing_evidence=["Insufficient fixture evidence"] if status == "UNKNOWN" else [],
            confidence=None if status == "UNKNOWN" else 0.8,
            judge_model=request.model,
            prompt_version=request.prompt_version,
        )
        return ProviderResponse(
            output_json=json.dumps(output),
            model=request.model,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        )


def test_corpus_is_stratified_unique_pinned_and_provisional() -> None:
    assert len(CASES) == len(LABELS) == 50
    assert len({c.observations for c in CASES}) == 50
    assert set(Counter(c.dimension for c in CASES).values()) == {10}
    assert set(Counter(c.severity for c in CASES).values()) == {10}
    assert Counter(c.split for c in CASES) == {"development": 25, "holdout": 25}
    assert set(Counter((c.split, c.severity) for c in CASES).values()) == {5}
    validate_labels(CASES, LABELS)
    assert all(label.review_status == "provisional" and not label.reviews for label in LABELS)
    assert {label.status for label in LABELS} == {"PASS", "REVISE", "FAIL", "UNKNOWN"}


def test_offline_all_cases_unknown_and_no_synthetic_confidence() -> None:
    predictions = predict(CASES, RUBRIC, OfflineProvider(), "offline")
    report = score(CASES, LABELS, predictions, RUBRIC)
    assert BenchmarkReport.model_validate_json(report.model_dump_json()) == report
    assert report.trials == report.provisional_labels == 50
    assert all(r.predicted_status == "UNKNOWN" and r.confidence is None for r in report.cases)
    assert report.metrics["known_prediction_coverage"].value == 0
    assert report.metrics["critical_violation_recall"].counts.denominator == 10
    assert report.metrics["critical_violation_recall"].value == 0
    assert report.metrics["violation_precision"].value is None
    assert report.metrics["citation_validity"].wilson95 is None
    assert report.confidence_brier is None
    assert len(report.disagreement_ids) == 45
    assert report.usage.cost_observations == 50 and report.usage.cost_usd_observed_total == 0


def test_known_confusion_counts_kappa_and_costs() -> None:
    cases, labels = subset(["FAIL", "FAIL", "PASS", "PASS"])
    predictions = predict(
        cases, RUBRIC, FixtureProvider(["FAIL", "PASS", "FAIL", "PASS"]), "fixture/v1"
    )
    report = score(cases, labels, predictions, RUBRIC)
    for key in (
        "violation_precision",
        "violation_recall",
        "false_approval_rate",
        "false_block_rate",
        "accuracy",
    ):
        assert report.metrics[key].value == 0.5
    assert report.agreement.value == 0
    assert report.agreement.pairs == 4
    assert len(report.disagreement_ids) == 2
    assert report.usage.cost_usd_observed_total == pytest.approx(0.04)
    assert report.usage.input_tokens_observed_total == 40
    assert report.confidence_brier == pytest.approx(0.34)


def test_wilson_known_example_and_boundary_uncertainty() -> None:
    assert rate(5, 10).wilson95 == pytest.approx((0.2365930905, 0.7634069095))
    perfect = rate(10, 10)
    assert perfect.wilson95 and 0.72 < perfect.wilson95[0] < 0.73
    zero = rate(0, 10)
    assert zero.wilson95 and 0.27 < zero.wilson95[1] < 0.28
    assert rate(0, 0).value is None
    with pytest.raises(ValueError):
        rate(2, 1)
    assert kappa([]).value is None
    assert kappa([("PASS", "PASS")] * 3).value is None
    assert kappa([("PASS", "PASS"), ("FAIL", "FAIL")]).value == 1
    assert kappa([("PASS", "FAIL"), ("FAIL", "PASS")]).value == -1


def test_missing_invalid_and_provider_error_remain_in_denominators() -> None:
    cases, labels = subset(["FAIL", "FAIL", "FAIL"])
    bad = predict(cases[:1], RUBRIC, FixtureProvider(["FAIL"], bad_citation=True), "fixture/v1")

    class Broken:
        def complete(self, request: JudgeRequest) -> ProviderResponse:
            raise RuntimeError("private transport diagnostic")

    failed = predict(cases[1:2], RUBRIC, Broken(), "fixture/v1")
    report = score(cases, labels, bad + failed, RUBRIC)
    assert [r.validity for r in report.cases] == ["invalid_output", "provider_error", "missing"]
    assert report.metrics["violation_recall"].counts.denominator == 3
    assert report.metrics["violation_recall"].value == 0
    assert report.metrics["citation_validity"].counts.denominator == 1
    assert report.metrics["citation_validity"].value == 0
    assert report.agreement.value is None
    assert report.usage.cost_observations == 1 and report.usage.latency_observations == 2
    assert "private transport diagnostic" not in report.model_dump_json()


def test_request_is_blind_and_changes_with_evidence_or_prompt_config() -> None:
    case = CASES[0]
    request, _ = request_for(case, RUBRIC, "fixture/v1")
    altered = case.model_copy(
        update={"severity": "critical", "split": "holdout", "family": "secret-reference"}
    )
    assert request_for(altered, RUBRIC, "fixture/v1")[0] == request
    assert "secret-reference" not in request.model_dump_json()
    assert "review_status" not in request.evidence_json
    changed = case.model_copy(update={"observations": "Different evidence"})
    assert request_revision(request_for(changed, RUBRIC, "fixture/v1")[0]) != request_revision(
        request
    )
    with pytest.raises(ValueError):
        request.model = "mutated"


@pytest.mark.parametrize("fault", ["duplicate", "foreign", "stale", "model"])
def test_prediction_identity_rejected(fault: str) -> None:
    cases, labels = subset(["PASS", "FAIL"])
    predictions = predict(cases, RUBRIC, FixtureProvider(["PASS", "FAIL"]), "fixture/v1")
    if fault == "duplicate":
        predictions += predictions[:1]
    else:
        updates = {
            "foreign": {"case_id": "foreign"},
            "stale": {"request_revision": "sha256:" + "0" * 64},
            "model": {"model": "different/v1"},
        }[fault]
        predictions = (predictions[0].model_copy(update=updates), predictions[1])
    with pytest.raises(ValueError):
        score(cases, labels, predictions, RUBRIC)


@pytest.mark.parametrize("fault", ["duplicate", "missing", "stale"])
def test_label_identity_rejected(fault: str) -> None:
    labels = LABELS
    if fault == "duplicate":
        labels += labels[:1]
    elif fault == "missing":
        labels = labels[1:]
    else:
        labels = (labels[0].model_copy(update={"case_revision": "sha256:" + "0" * 64}), *labels[1:])
    with pytest.raises(ValueError):
        validate_labels(CASES, labels)


def test_human_review_requires_independent_records_and_adjudication() -> None:
    label = LABELS[0].model_dump()
    label["review_status"] = "adjudicated"
    with pytest.raises(ValueError):
        Label.model_validate(label)
    label["reviews"] = (
        Review(reviewer="alice", status="PASS", rationale="Evidence checked"),
        Review(reviewer="bob", status="FAIL", rationale="Contract broken"),
    )
    with pytest.raises(ValueError):
        Label.model_validate(label)
    label.update(adjudicator="carol", adjudication="Resolved conflicting contract interpretation")
    assert Label.model_validate(label).review_status == "adjudicated"
    label["adjudicator"] = "alice"
    with pytest.raises(ValueError):
        Label.model_validate(label)


def test_strict_input_duplicate_keys_and_family_leakage(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        CASES[0]
        .model_dump_json()
        .replace('"schema_version":"1"', '"schema_version":"1","schema_version":"1"')
        + "\n"
    )
    with pytest.raises(ValueError, match="duplicate JSON"):
        load_cases(path)
    other = CASES[1].model_copy(
        update={
            "family": CASES[0].family,
            "split": "holdout" if CASES[0].split == "development" else "development",
        }
    )
    path.write_text(CASES[0].model_dump_json() + "\n" + other.model_dump_json() + "\n")
    with pytest.raises(ValueError, match="leaks"):
        load_cases(path)
    path.write_text(CASES[0].model_dump_json() + "\n\n")
    with pytest.raises(ValueError, match="blank"):
        load_cases(path)


@pytest.mark.parametrize("output", ["{}", "not JSON", '{"status":"PASS","status":"FAIL"}'])
def test_invalid_output_is_reported_not_dropped(output: str) -> None:
    cases, labels = subset(["FAIL"])
    predictions = predict(cases, RUBRIC, FixtureProvider(["PASS"]), "fixture/v1")
    response = predictions[0].response
    assert response
    predictions = (
        predictions[0].model_copy(
            update={"response": response.model_copy(update={"output_json": output})}
        ),
    )
    report = score(cases, labels, predictions, RUBRIC)
    assert report.cases[0].validity == "invalid_output"
    assert report.metrics["valid_output_coverage"].value == 0


def test_cli_offline_export_and_scoring_roundtrip(tmp_path: Path) -> None:
    runner = CliRunner()
    exported = runner.invoke(
        app, ["benchmark", "export", "--model", "fixture/v1", "--split", "holdout"]
    )
    assert exported.exit_code == 0, exported.output
    assert len(exported.stdout.splitlines()) == 25
    assert all(
        set(json.loads(line)) == {"schema_version", "case_id", "request_revision", "request"}
        for line in exported.stdout.splitlines()
    )
    result = runner.invoke(app, ["benchmark", "run", "--offline", "--split", "holdout"])
    assert result.exit_code == 0, result.output
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(result.stdout)
    assert len(load_jsonl(predictions, Prediction)) == 25
    result = runner.invoke(app, ["benchmark", "score", str(predictions), "--split", "holdout"])
    assert result.exit_code == 0, result.output
    report = BenchmarkReport.model_validate_json(result.stdout)
    assert report.trials == 25
    assert report.metrics["known_prediction_coverage"].value == 0
    bad = runner.invoke(app, ["benchmark", "score", str(predictions), "--split", "development"])
    assert bad.exit_code == 2 and not bad.stdout
    assert runner.invoke(app, ["benchmark", "run"]).exit_code == 3


def test_missing_usage_is_not_imputed(tmp_path: Path) -> None:
    cases, labels = subset(["PASS"])
    prediction = predict(cases, RUBRIC, FixtureProvider(["PASS"]), "fixture/v1")[0]
    assert prediction.response
    response = prediction.response.model_copy(
        update={"cost_usd": None, "input_tokens": None, "output_tokens": None}
    )
    report = score(cases, labels, (prediction.model_copy(update={"response": response}),), RUBRIC)
    assert report.usage.cost_observations == report.usage.input_token_observations == 0
    assert report.usage.trials == 1
    assert report.usage.cost_usd_observed_total == 0  # observed subtotal, not a claimed total


def test_explicit_unknown_matches_unknown_but_missing_never_does() -> None:
    cases, labels = subset(["UNKNOWN", "UNKNOWN"])
    predictions = predict(cases[:1], RUBRIC, FixtureProvider(["UNKNOWN"]), "fixture/v1")
    report = score(cases, labels, predictions, RUBRIC)
    assert report.metrics["accuracy"].counts.numerator == 1
    assert report.metrics["accuracy"].counts.denominator == 2
    assert report.agreement.pairs == 1
    assert report.cases[0].validity == "valid"
    assert report.cases[1].validity == "missing"
    assert report.disagreement_ids == (cases[1].case_id,)


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_provider_usage_is_not_recorded_as_valid(value: float) -> None:
    class InvalidUsage(FixtureProvider):
        def complete(self, request: JudgeRequest) -> ProviderResponse:
            return super().complete(request).model_copy(update={"cost_usd": value})

    cases, labels = subset(["FAIL"])
    predictions = predict(cases, RUBRIC, InvalidUsage(["PASS"]), "fixture/v1")
    report = score(cases, labels, predictions, RUBRIC)
    assert report.cases[0].validity == "provider_error"
    assert report.usage.cost_observations == 0
    assert report.metrics["valid_output_coverage"].value == 0
