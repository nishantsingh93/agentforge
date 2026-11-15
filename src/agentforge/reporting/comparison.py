"""Baseline comparisons preserve both populations, without imputing missing scores."""

from agentforge.core.schemas import Metric, Versioned
from agentforge.core.trace import canonical_json
from agentforge.reporting.json_report import ReportDocument


class CountComparison(Versioned):
    baseline: Metric | None
    current: Metric | None
    rate_delta: float | None


class Comparison(Versioned):
    baseline: ReportDocument
    current: ReportDocument
    outcomes: dict[str, CountComparison]
    metrics: dict[str, CountComparison]
    quality_delta: float | None
    warnings: tuple[str, ...]


def _counts(before: Metric | None, after: Metric | None) -> CountComparison:
    delta = None
    if before and after and before.denominator and after.denominator:
        delta = after.numerator / after.denominator - before.numerator / before.denominator
    return CountComparison(schema_version="1", baseline=before, current=after, rate_delta=delta)


def compare(baseline: ReportDocument, current: ReportDocument) -> Comparison:
    def population(document: ReportDocument) -> list[str]:
        return sorted(r.attempt.scenario_id for r in document.runs)

    warnings = []
    matching = population(baseline) == population(current)
    if not matching:
        warnings.append("Scenario populations differ; aggregate deltas are not paired effects.")
    configs = [
        sorted(
            (r.attempt.scenario_id, canonical_json(r.attempt.report.config).decode())
            for r in d.runs
            if r.attempt.report
        )
        for d in (baseline, current)
    ]
    if configs[0] != configs[1]:
        warnings.append("Run configurations differ; inspect pinned revisions and model settings.")
    scores = [
        [r.attempt.report.weighted_quality if r.attempt.report else None for r in d.runs]
        for d in (baseline, current)
    ]
    quality_delta = None
    if matching and all(s is not None for group in scores for s in group):
        means = [sum(s for s in group if s is not None) / len(group) for group in scores]
        quality_delta = means[1] - means[0]
    metrics = {}
    for key in sorted(baseline.metrics.keys() | current.metrics.keys()):
        before, after = baseline.metrics.get(key), current.metrics.get(key)
        item = _counts(before.counts if before else None, after.counts if after else None)
        if any(m is None or m.observed_runs != m.total_runs for m in (before, after)):
            item = item.model_copy(update={"rate_delta": None})
            warnings.append(f"{key}: incomplete coverage; rate delta UNKNOWN.")
        metrics[key] = item
    return Comparison(
        schema_version="1",
        baseline=baseline,
        current=current,
        outcomes={
            key: _counts(baseline.outcomes[key], current.outcomes[key]) for key in baseline.outcomes
        },
        metrics=metrics,
        quality_delta=quality_delta,
        warnings=tuple(warnings),
    )
