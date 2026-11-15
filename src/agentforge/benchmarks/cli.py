"""Benchmark commands output JSON artifacts without executing scenario actions."""

from pathlib import Path
from typing import Annotated

import typer

from agentforge.benchmarks.data import (
    BlindInput,
    Case,
    Label,
    load_cases,
    load_jsonl,
    request_for,
    request_revision,
    validate_labels,
)
from agentforge.benchmarks.harness import Prediction, predict
from agentforge.benchmarks.scoring import score
from agentforge.evaluation.rubrics import load_rubric
from agentforge.providers.offline import OfflineProvider

app = typer.Typer(help="Read-only judge benchmark: blinded inputs, predictions and metrics.")


def _cases(path: Path, split: str) -> tuple[Case, ...]:
    if split not in {"development", "holdout", "all"}:
        raise ValueError("invalid split")
    cases = load_cases(path)
    selected = tuple(c for c in cases if split == "all" or c.split == split)
    if not selected:
        raise ValueError("empty selected split")
    return selected


def _invalid() -> None:
    typer.echo("Invalid benchmark inputs; check schemas, IDs, revisions and split.", err=True)
    raise typer.Exit(2)


@app.command("export")
def export_inputs(
    model: Annotated[str, typer.Option(help="Pinned provider/model version.")],
    cases: Path = Path("benchmarks/cases.jsonl"),
    split: str = "development",
    root: Path = Path("."),
) -> None:
    """Export blinded JudgeRequest JSONL; labels are never read."""
    try:
        rubric = load_rubric(root)
        rows = []
        for case in _cases(cases, split):
            request, _ = request_for(case, rubric, model)
            rows.append(
                BlindInput(
                    schema_version="1",
                    case_id=case.case_id,
                    request_revision=request_revision(request),
                    request=request,
                )
            )
        output = "\n".join(r.model_dump_json() for r in rows)
    except (OSError, ValueError, RecursionError):
        _invalid()
        return
    typer.echo(output)


@app.command("run")
def run_offline(
    offline: Annotated[
        bool, typer.Option(help="Required; UNKNOWN predictions, no model calls.")
    ] = False,
    cases: Path = Path("benchmarks/cases.jsonl"),
    split: str = "development",
    root: Path = Path("."),
) -> None:
    """Collect offline prediction JSONL; use the provider API for model-backed runs."""
    if not offline:
        typer.echo(
            "No network provider installed; use --offline or the Python provider API.", err=True
        )
        raise typer.Exit(3)
    try:
        results = predict(_cases(cases, split), load_rubric(root), OfflineProvider(), "offline")
        output = "\n".join(r.model_dump_json() for r in results)
    except (OSError, ValueError, RecursionError):
        _invalid()
        return
    typer.echo(output)


@app.command("score")
def score_predictions(
    predictions: Path,
    cases: Path = Path("benchmarks/cases.jsonl"),
    labels: Path = Path("benchmarks/labels.jsonl"),
    split: str = "development",
    root: Path = Path("."),
) -> None:
    """Compare recorded predictions and labels; exit 0 means report produced, not safe."""
    try:
        all_cases = load_cases(cases)
        all_labels = load_jsonl(labels, Label)
        validate_labels(all_cases, all_labels)
        selected = _cases(cases, split)
        ids = {c.case_id for c in selected}
        result = score(
            selected,
            tuple(label for label in all_labels if label.case_id in ids),
            load_jsonl(predictions, Prediction),
            load_rubric(root),
        )
        output = result.model_dump_json(indent=2)
    except (OSError, ValueError, RecursionError):
        _invalid()
        return
    typer.echo(output)
