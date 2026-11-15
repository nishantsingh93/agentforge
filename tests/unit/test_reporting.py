"""Reporting consumes recorded artifacts, never executes an agent or a command."""

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_runner import execute
from test_sandbox import FakeDocker
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.core.runner import AttemptResult, publish
from agentforge.core.schemas import Metric
from agentforge.reporting.comparison import compare
from agentforge.reporting.html_report import render_html
from agentforge.reporting.json_report import MetricSummary, ReportDocument, load_report


@pytest.fixture
def document(tmp_path: Path) -> ReportDocument:
    suite = execute(tmp_path, FakeDocker())
    return load_report(tmp_path, suite.run_id)


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        for key, value in attrs:
            if key == "id" and value:
                self.ids.append(value)
            if key == "href" and value:
                self.hrefs.append(value)
            assert not key.startswith("on")


def test_offline_report_roundtrip_and_internal_links(document: ReportDocument) -> None:
    assert ReportDocument.model_validate_json(document.model_dump_json()) == document
    assert document.outcomes["Bullseye"] == Metric(numerator=2, denominator=2)
    assert document.missing_metrics == ("unsafe_action_attempts", "unsafe_action_escapes")
    html = render_html(document)
    assert html.count("<td>UNKNOWN</td>") == 30  # status, score, confidence, five judges, two runs
    assert "unsafe_action_escapes: UNKNOWN" in html
    parser = Elements()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    assert parser.hrefs and all(href[1:] in parser.ids for href in parser.hrefs)
    assert "script" not in parser.tags and "iframe" not in parser.tags


def test_untrusted_text_is_never_markup(document: ReportDocument) -> None:
    detail = document.runs[0]
    assert detail.attempt.report
    attack = '</pre><script>alert(1)</script><img src=x onerror="alert(2)">'
    report = detail.attempt.report.model_copy(update={"config": {"attack": attack}})
    detail = detail.model_copy(
        update={"attempt": detail.attempt.model_copy(update={"report": report})}
    )
    html = render_html(document.model_copy(update={"runs": (detail,)}))
    assert attack not in html and "&lt;script&gt;" in html
    parser = Elements()
    parser.feed(html)
    assert "script" not in parser.tags and "img" not in parser.tags


def test_counts_and_denominators_are_summed_not_averaged(document: ReportDocument) -> None:
    before = document.model_copy(
        update={
            "metrics": {
                "escape": MetricSummary(
                    schema_version="1",
                    counts=Metric(numerator=1, denominator=2),
                    observed_runs=2,
                    total_runs=2,
                )
            }
        }
    )
    after = document.model_copy(
        update={
            "metrics": {
                "escape": MetricSummary(
                    schema_version="1",
                    counts=Metric(numerator=1, denominator=10),
                    observed_runs=2,
                    total_runs=2,
                )
            }
        }
    )
    result = compare(before, after)
    assert result.metrics["escape"].baseline == Metric(numerator=1, denominator=2)
    assert result.metrics["escape"].current == Metric(numerator=1, denominator=10)
    assert result.metrics["escape"].rate_delta == pytest.approx(-0.4)
    assert result.quality_delta is None
    assert "1/2" in render_html(after, result) and "1/10" in render_html(after, result)
    absent = compare(before, document)
    assert absent.metrics["escape"].current is None
    assert absent.metrics["escape"].rate_delta is None


def test_zero_denominator_and_partial_coverage(document: ReportDocument) -> None:
    for denominator, coverage in ((0, 2), (3, 1)):
        changed = document.model_copy(
            update={
                "metrics": {
                    "refused_actions": MetricSummary(
                        schema_version="1",
                        counts=Metric(numerator=0, denominator=denominator),
                        observed_runs=coverage,
                        total_runs=2,
                    )
                }
            }
        )
        assert compare(document, changed).metrics["refused_actions"].rate_delta is None


def test_cli_report_and_compare(tmp_path: Path, document: ReportDocument) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["report", document.run_id, "--runs-root", str(tmp_path)])
    assert result.exit_code == 0 and result.stdout.startswith("<!doctype html>")
    result = runner.invoke(
        app,
        [
            "report",
            document.runs[0].attempt.run_id,
            "--format",
            "json",
            "--runs-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)["runs"]) == 1
    result = runner.invoke(
        app, ["compare", document.run_id, document.run_id, "--runs-root", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["quality_delta"] is None
    assert json.loads(result.stdout)["outcomes"]["Bullseye"]["rate_delta"] == 0


@pytest.mark.parametrize("run_id", ["../outside", "/tmp", "..", "bad/name"])
def test_reject_traversal(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError):
        load_report(tmp_path, run_id)


@pytest.mark.parametrize("artifact", ["report.json", "evidence.json", "trace.jsonl"])
def test_corrupt_artifact_is_rejected(
    tmp_path: Path, document: ReportDocument, artifact: str
) -> None:
    (tmp_path / document.runs[0].attempt.run_id / artifact).write_text("{}")
    result = CliRunner().invoke(app, ["report", document.run_id, "--runs-root", str(tmp_path)])
    assert result.exit_code == 2 and not result.stdout


def test_symlink_rejected(tmp_path: Path, document: ReportDocument) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path / document.run_id, target_is_directory=True)
    with pytest.raises(OSError):
        load_report(tmp_path, "alias")
    detail = document.runs[0]
    path = tmp_path / detail.attempt.run_id / "evidence.json"
    external = tmp_path / "outside.json"
    path.rename(external)
    path.symlink_to(external)
    with pytest.raises(OSError):
        load_report(tmp_path, document.run_id)


def test_error_run_is_unknown_and_counted(tmp_path: Path) -> None:
    directory = tmp_path / "failed"
    directory.mkdir()
    publish(
        directory,
        "result.json",
        AttemptResult(
            schema_version="1",
            run_id="failed",
            scenario_id="F01",
            status="error",
            exit_code=3,
            report=None,
            error="Interrupted",
        ),
    )
    document = load_report(tmp_path, "failed")
    assert document.outcomes["UNKNOWN"] == Metric(numerator=1, denominator=1)
    assert "Report unavailable" in render_html(document)


def test_population_difference_is_explicit(document: ReportDocument, tmp_path: Path) -> None:
    single = load_report(tmp_path, document.runs[0].attempt.run_id)
    result = compare(document, single)
    assert result.warnings and result.quality_delta is None
    assert result.outcomes["Bullseye"].baseline == Metric(numerator=2, denominator=2)
    assert result.outcomes["Bullseye"].current == Metric(numerator=1, denominator=1)


def test_different_outcomes_and_aggregation(tmp_path: Path, document: ReportDocument) -> None:
    flawed = execute(tmp_path, FakeDocker(), flawed=True)
    current = load_report(tmp_path, flawed.run_id)
    result = compare(document, current)
    assert result.outcomes["Misleading"].current == Metric(numerator=1, denominator=2)
    assert result.outcomes["Misleading"].rate_delta == 0.5
    expected = sum(
        r.attempt.report.metrics["refused_actions"].denominator
        for r in current.runs
        if r.attempt.report
    )
    assert current.metrics["refused_actions"].counts.denominator == expected


def test_citation_mismatch_rejected(tmp_path: Path, document: ReportDocument) -> None:
    detail = document.runs[0]
    assert detail.attempt.report
    report = detail.attempt.report
    reference = report.audit_artifacts[0].model_copy(update={"revision": "sha256:" + "0" * 64})
    report = report.model_copy(update={"audit_artifacts": (reference,)})
    directory = tmp_path / detail.attempt.run_id
    (directory / "report.json").write_text(report.model_dump_json())
    (directory / "result.json").write_text(
        detail.attempt.model_copy(update={"report": report}).model_dump_json()
    )
    with pytest.raises(ValueError, match="citation"):
        load_report(tmp_path, detail.attempt.run_id)


def test_object_tampering_rejected(tmp_path: Path, document: ReportDocument) -> None:
    detail = document.runs[0]
    assert detail.evidence
    ref = detail.evidence.inspected_files[0]
    (tmp_path / detail.attempt.run_id / "objects" / ref.revision[7:]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="revision mismatch"):
        load_report(tmp_path, document.run_id)


def test_duplicate_suite_attempt_rejected(tmp_path: Path, document: ReportDocument) -> None:
    path = tmp_path / document.run_id / "summary.json"
    payload = json.loads(path.read_text())
    payload["attempts"].append(payload["attempts"][0])
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="duplicate"):
        load_report(tmp_path, document.run_id)
