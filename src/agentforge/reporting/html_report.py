"""Self-contained, script-free HTML; every data value is escaped at insertion."""

import json
from html import escape

from agentforge.core.schemas import EvidenceRef, Metric
from agentforge.reporting.comparison import Comparison
from agentforge.reporting.json_report import ReportDocument


def _text(value: object) -> str:
    return escape("UNKNOWN" if value is None else str(value), quote=True)


def _pre(value: object) -> str:
    text = (
        json.dumps(value, indent=2, ensure_ascii=False)
        if isinstance(value, (dict, list))
        else value
    )
    return "<pre>" + _text(text) + "</pre>"


def _count(value: Metric | None) -> str:
    if value is None:
        return "UNKNOWN"
    rate = f"{value.numerator / value.denominator:.1%}" if value.denominator else "UNKNOWN"
    return f"{value.numerator}/{value.denominator} ({rate})"


def _citation(run_id: str, ref: EvidenceRef) -> str:
    target = ref.event_id if ref.kind == "event" else ref.revision[7:]
    label = ref.event_id if ref.kind == "event" else f"{ref.path}:{ref.start_line}–{ref.end_line}"
    return f'<a href="#{_text(run_id)}-{_text(target)}">{_text(label)}</a> {_text(ref.revision)}'


def _body(document: ReportDocument) -> str:
    parts = [
        f"<h1>AgentForge report: {_text(document.run_id)}</h1>",
        f"<p>Evaluation exit code: {document.exit_code}. Trials: {len(document.runs)}.</p>",
        "<p>Quality, safety and outcome are independent. UNKNOWN is not a pass. "
        "Seeded evaluations do not establish production safety.</p>",
        "<h2>Outcome distribution</h2><ul>",
    ]
    parts.extend(f"<li>{_text(k)}: {_count(v)}</li>" for k, v in document.outcomes.items())
    parts.append("</ul><h2>Safety and observed metrics</h2><ul>")
    parts.extend(
        f"<li>{_text(k)}: {_count(v.counts)}; coverage {v.observed_runs}/{v.total_runs} runs</li>"
        for k, v in document.metrics.items()
    )
    parts.extend(f"<li>{_text(k)}: UNKNOWN — not measured</li>" for k in document.missing_metrics)
    parts.append("</ul><p>Refused actions are not equivalent to unsafe attempts or escapes.</p>")
    for detail in document.runs:
        attempt = detail.attempt
        run_id = attempt.run_id
        parts.append(f"<section><h2>{_text(attempt.scenario_id)} · {_text(run_id)}</h2>")
        parts.append(f"<p>Status: {_text(attempt.status)}; exit: {attempt.exit_code}</p>")
        if attempt.error:
            parts.append(_pre(attempt.error))
        report = attempt.report
        if report is None:
            parts.append(
                "<p>Report unavailable; quality, safety and outcome UNKNOWN.</p></section>"
            )
            continue
        parts.append(
            f"<p>Quality: {_text(report.quality_status)} / {_text(report.weighted_quality)}; "
            f"Safety: {_text(report.safety)}; Outcome: "
            f"{_text(report.outcome.category if report.outcome else None)}; "
            f"Release decision: {_text(report.release_decision)}</p>"
        )
        parts.append("<h3>Configuration</h3>" + _pre(report.config))
        parts.append(
            "<h3>Five rubric judgments</h3><table><thead><tr><th>Dimension</th>"
            "<th>Status</th><th>Score</th><th>Confidence</th><th>Model / prompt</th>"
            "</tr></thead><tbody>"
        )
        for judge in report.judges:
            parts.append(
                "<tr>"
                + "".join(
                    f"<td>{_text(v)}</td>"
                    for v in (
                        judge.dimension,
                        judge.status,
                        judge.score,
                        judge.confidence,
                        f"{judge.judge_model} / {judge.prompt_version}",
                    )
                )
                + "</tr>"
            )
        parts.append("</tbody></table><h3>Findings and uncertainty</h3>")
        for judge in report.judges:
            parts.append(f"<h4>{_text(judge.dimension)}</h4>")
            parts.extend(_pre(missing) for missing in judge.missing_evidence)
            parts.extend("<p>" + _citation(run_id, ref) + "</p>" for ref in judge.evidence)
            for finding in judge.findings:
                parts.append(_pre(f"{finding.severity}: {finding.claim}\n{finding.recommendation}"))
                parts.extend("<p>" + _citation(run_id, ref) + "</p>" for ref in finding.evidence)
        parts.append("<h3>Audit and outcome evidence</h3>")
        refs = (*report.audit_artifacts, *(report.outcome.evidence if report.outcome else ()))
        parts.extend("<p>" + _citation(run_id, ref) + "</p>" for ref in refs)
        if detail.evidence:
            parts.append("<h3>Patch</h3>" + _pre(detail.evidence.diff))
            parts.append("<h3>Observed checks</h3>")
            parts.extend(_pre(c.model_dump(mode="json")) for c in detail.evidence.commands)
            parts.append("<h3>State snapshots / health and rollback evidence</h3>")
            parts.extend(_pre(s.model_dump(mode="json")) for s in detail.evidence.snapshots)
            parts.append(
                "<p>Only recorded observations are shown; absent health or rollback "
                "evidence is UNKNOWN.</p><h3>Files</h3>"
            )
            seen = set()
            for ref in detail.evidence.inspected_files:
                # Identical file bytes may share an object; one anchor per digest.
                anchor = "" if ref.revision in seen else f' id="{_text(run_id)}-{ref.revision[7:]}"'
                seen.add(ref.revision)
                parts.append(
                    f"<details{anchor}><summary>{_text(ref.path)} "
                    f"{_text(ref.revision)}</summary>" + _pre(detail.files[ref.path]) + "</details>"
                )
        parts.append("<h3>Trace and policy timeline</h3>")
        for event in detail.events:
            parts.append(
                f'<details id="{_text(run_id)}-{_text(event.event_id)}">'
                f"<summary>{event.sequence} · {_text(event.timestamp)} · "
                f"{_text(event.actor)}</summary>"
                + _pre(event.model_dump(mode="json"))
                + "</details>"
            )
        parts.append("</section>")
    return "\n".join(parts)


def render_html(document: ReportDocument, comparison: Comparison | None = None) -> str:
    prefix = ""
    if comparison:
        if comparison.current != document:
            raise ValueError("comparison current run differs from report")
        prefix = f"<h2>Baseline comparison: {_text(comparison.baseline.run_id)}</h2>"
        prefix += f"<p>Quality delta: {_text(comparison.quality_delta)}</p>"
        prefix += "".join(_pre(w) for w in comparison.warnings)
        prefix += (
            "<table><tr><th>Metric</th><th>Baseline</th><th>Current</th><th>Rate delta</th></tr>"
        )
        for key, counts in (*comparison.outcomes.items(), *comparison.metrics.items()):
            prefix += (
                f"<tr><td>{_text(key)}</td><td>{_count(counts.baseline)}</td>"
                f"<td>{_count(counts.current)}</td><td>{_text(counts.rate_delta)}</td></tr>"
            )
        prefix += "</table>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>AgentForge evaluation report</title><style>"
        "body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f6;padding:1rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.5rem;"
        "text-align:left}section{border-top:2px solid #777;margin-top:2rem}"
        "details{margin:.5rem 0}a{overflow-wrap:anywhere}</style></head><body>"
        + prefix
        + _body(document)
        + "</body></html>\n"
    )
