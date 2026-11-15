"""Bounded artifact loading and lossless report aggregation."""

import os
import re
import stat
from pathlib import Path

from agentforge.core.artifacts import MAX_ARTIFACT_BYTES
from agentforge.core.runner import AttemptResult, SuiteResult
from agentforge.core.schemas import EvidenceBundle, Metric, RunReport, TraceEvent, Versioned
from agentforge.core.trace import replay_trace
from agentforge.judges.context import prepare_evidence

OUTCOMES = ("Bullseye", "Directional", "Good Triage", "Partial", "Misleading", "UNKNOWN")


class RunDetail(Versioned):
    attempt: AttemptResult
    evidence: EvidenceBundle | None
    events: tuple[TraceEvent, ...]
    files: dict[str, str]


class MetricSummary(Versioned):
    counts: Metric
    observed_runs: int
    total_runs: int


class ReportDocument(Versioned):
    run_id: str
    exit_code: int
    runs: tuple[RunDetail, ...]
    outcomes: dict[str, Metric]
    metrics: dict[str, MetricSummary]
    missing_metrics: tuple[str, ...]


def read_artifact(root: Path, run_id: str, name: str) -> bytes:
    """Open only fixed artifact names or digest objects beneath a validated run ID."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id) is None:
        raise ValueError("invalid run identifier")
    if name not in {"summary.json", "result.json", "report.json", "evidence.json", "trace.jsonl"}:
        if re.fullmatch(r"objects/[a-f0-9]{64}", name) is None:
            raise ValueError("invalid artifact name")
    descriptors = []
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in (run_id, *name.split("/")[:-1]):
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        file_fd = os.open(
            name.split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        with os.fdopen(file_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
                raise ValueError("invalid or oversized artifact")
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError("oversized artifact")
        return data
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _detail(root: Path, attempt: AttemptResult) -> RunDetail:
    report = attempt.report
    evidence = None
    events: tuple[TraceEvent, ...] = ()
    files: dict[str, str] = {}
    if report is not None:
        if report.run_id != attempt.run_id or report.scenario_id != attempt.scenario_id:
            raise ValueError("attempt/report identity mismatch")
        persisted = RunReport.model_validate_json(
            read_artifact(root, attempt.run_id, "report.json")
        )
        if persisted != report:
            raise ValueError("summary/report mismatch")
        evidence = EvidenceBundle.model_validate_json(
            read_artifact(root, attempt.run_id, "evidence.json")
        )
        if evidence.run_id != report.run_id:
            raise ValueError("evidence identity mismatch")
        trace = read_artifact(root, attempt.run_id, "trace.jsonl")
        raw_files = {
            ref.path: read_artifact(root, attempt.run_id, "objects/" + ref.revision[7:])
            for ref in evidence.inspected_files
        }
        prepare_evidence(evidence, files=raw_files, trace=trace)
        events = tuple(record.event for record in replay_trace(trace))
        files = {path: content.decode("utf-8") for path, content in raw_files.items()}
        refs = [*report.audit_artifacts]
        if report.outcome:
            refs.extend(report.outcome.evidence)
        for judge in report.judges:
            refs.extend(judge.evidence)
            for finding in judge.findings:
                refs.extend(finding.evidence)
        for ref in refs:
            if ref.kind == "event":
                if ref not in evidence.events:
                    raise ValueError("unresolved event citation")
            elif not any(
                f.path == ref.path
                and f.revision == ref.revision
                and f.start_line <= ref.start_line <= ref.end_line <= f.end_line
                for f in evidence.inspected_files
            ):
                raise ValueError("unresolved file citation")
    elif attempt.status != "error":
        raise ValueError("completed attempt has no report")
    return RunDetail(
        schema_version="1", attempt=attempt, evidence=evidence, events=events, files=files
    )


def load_report(root: Path, run_id: str) -> ReportDocument:
    attempts: tuple[AttemptResult, ...]
    try:
        summary = read_artifact(root, run_id, "summary.json")
    except FileNotFoundError:
        attempt = AttemptResult.model_validate_json(read_artifact(root, run_id, "result.json"))
        if attempt.run_id != run_id:
            raise ValueError("run identity mismatch") from None
        attempts, exit_code = (attempt,), attempt.exit_code
    else:
        suite = SuiteResult.model_validate_json(summary)
        if suite.run_id != run_id or not suite.attempts:
            raise ValueError("invalid suite identity or empty suite")
        attempts, exit_code = suite.attempts, suite.exit_code
        if len({a.run_id for a in attempts}) != len(attempts):
            raise ValueError("duplicate attempt")
        for attempt in attempts:
            stored = AttemptResult.model_validate_json(
                read_artifact(root, attempt.run_id, "result.json")
            )
            if stored != attempt:
                raise ValueError("suite/attempt mismatch")
    runs = tuple(_detail(root, attempt) for attempt in attempts)
    reports = [a.report for a in attempts if a.report is not None]
    outcomes = {
        category: Metric(
            numerator=sum(
                (a.report.outcome.category if a.report and a.report.outcome else "UNKNOWN")
                == category
                for a in attempts
            ),
            denominator=len(attempts),
        )
        for category in OUTCOMES
    }
    metrics = {}
    for name in sorted({key for report in reports for key in report.metrics}):
        observed = [r.metrics[name] for r in reports if name in r.metrics]
        metrics[name] = MetricSummary(
            schema_version="1",
            counts=Metric(
                numerator=sum(m.numerator for m in observed),
                denominator=sum(m.denominator for m in observed),
            ),
            observed_runs=len(observed),
            total_runs=len(attempts),
        )
    return ReportDocument(
        schema_version="1",
        run_id=run_id,
        exit_code=exit_code,
        runs=runs,
        outcomes=outcomes,
        metrics=metrics,
        missing_metrics=tuple(
            name
            for name in ("unsafe_action_attempts", "unsafe_action_escapes")
            if name not in metrics
        ),
    )
