"""Real offline CLI subprocesses; no Docker or provider credentials are required."""

import hashlib
import subprocess
import sys
from pathlib import Path

from agentforge.benchmarks.data import BlindInput, load_jsonl
from agentforge.benchmarks.scoring import BenchmarkReport

ROOT = Path(__file__).resolve().parents[2]


def test_real_offline_benchmark_artifacts(tmp_path: Path) -> None:
    sources = [ROOT / "benchmarks/cases.jsonl", ROOT / "benchmarks/labels.jsonl"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    predictions = tmp_path / "predictions.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "agentforge", "benchmark", "run", "--offline", "--split", "all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    predictions.write_text(result.stdout)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "benchmark",
            "score",
            str(predictions),
            "--split",
            "all",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = BenchmarkReport.model_validate_json(result.stdout)
    assert report.trials == 50 and report.provisional_labels == 50
    assert report.metrics["known_prediction_coverage"].value == 0
    assert report.metrics["critical_violation_recall"].value == 0
    assert report.confidence_brier is None
    assert all(row.validity == "valid" for row in report.cases)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "benchmark",
            "export",
            "--model",
            "fixture/v1",
            "--split",
            "holdout",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    exported = tmp_path / "blind.jsonl"
    exported.write_text(result.stdout)
    assert len(load_jsonl(exported, BlindInput)) == 25
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
