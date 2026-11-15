"""Read-only registry validation on disposable copies of owned fixtures."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.core.scenario import (
    ScenarioError,
    load_registry,
    parse_scenario,
    validate_registered,
)

PROJECT = Path(__file__).resolve().parents[2]
SCENARIO = "scenarios/correctness/F01.yaml"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for directory in ("fixtures", "faults", "scenarios"):
        shutil.copytree(PROJECT / directory, tmp_path / directory)
    return tmp_path


def test_registered_scenario_and_immutable_fixture(project: Path) -> None:
    entries = load_registry(project)
    assert [entry.scenario.id for entry in entries] == [f"F{i:02d}" for i in range(1, 11)]
    assert entries[0].scenario.id == "F01"
    assert entries[0].fixture.digest == entries[0].scenario.fixture.split("@", 1)[1]
    assert b"return status.lower()" in entries[0].fault
    original = entries[0].fixture.files[0].content
    (project / "fixtures/order-service/orders.py").write_text("changed")
    assert entries[0].fixture.files[0].content == original
    with pytest.raises(ScenarioError, match="digest mismatch"):
        load_registry(project)


@pytest.mark.parametrize(
    "data",
    [
        b"id: F01\nid: F02\n",
        b"a: &a [1]\nb: *a\n",
        b"!!python/object/apply:os.system ['echo unsafe']",
        b"1: value\n",
        b"a: .nan\n",
        b"a: 2026-11-06\n",
        b"a: !!binary aGVsbG8=\n",
        b"a: {<<: {id: F01}}\n",
        b"a: [unterminated",
        b"id: F01\n---\nid: F02\n",
        b"\xff",
        b"[" * 40 + b"0" + b"]" * 40,
        b"x" * 65_537,
    ],
)
def test_reject_unsafe_or_invalid_yaml(data: bytes) -> None:
    with pytest.raises(ScenarioError):
        parse_scenario(data)


def test_unknown_and_duplicate_registry_paths(project: Path) -> None:
    with pytest.raises(ScenarioError, match="not listed"):
        validate_registered(project, "scenarios/unknown.yaml")
    path = project / "scenarios/registry.json"
    registry = json.loads(path.read_text())
    registry["scenarios"] *= 2
    path.write_text(json.dumps(registry))
    with pytest.raises(ScenarioError, match="duplicate scenario path"):
        load_registry(project)


def test_duplicate_scenario_ids(project: Path) -> None:
    path = project / "scenarios/registry.json"
    registry = json.loads(path.read_text())
    duplicate = "scenarios/correctness/duplicate.yaml"
    shutil.copyfile(project / SCENARIO, project / duplicate)
    registry["scenarios"].append(duplicate)
    path.write_text(json.dumps(registry))
    with pytest.raises(ScenarioError, match="duplicate scenario ID"):
        load_registry(project)


def test_duplicate_registry_json_key(project: Path) -> None:
    (project / "scenarios/registry.json").write_text('{"schema_version":"1","schema_version":"1"}')
    with pytest.raises(ScenarioError, match="duplicate registry key"):
        load_registry(project)


def test_deep_registry_json_is_input_error(project: Path) -> None:
    (project / "scenarios/registry.json").write_text("[" * 2000 + "0" + "]" * 2000)
    with pytest.raises(ScenarioError):
        load_registry(project)
    result = CliRunner().invoke(app, ["scenarios", "list", "--root", str(project)])
    assert result.exit_code == 2


@pytest.mark.parametrize("path", ["../outside.yaml", "/etc/passwd", "faults/not-a-scenario.yaml"])
def test_registry_path_traversal(project: Path, path: str) -> None:
    registry_path = project / "scenarios/registry.json"
    registry = json.loads(registry_path.read_text())
    registry["scenarios"] = [path]
    registry_path.write_text(json.dumps(registry))
    with pytest.raises(ScenarioError):
        load_registry(project)


def test_scenario_symlink_and_missing_fault(project: Path) -> None:
    scenario = project / SCENARIO
    data = scenario.read_bytes()
    scenario.unlink()
    (project / "outside.yaml").write_bytes(data)
    scenario.symlink_to(project / "outside.yaml")
    with pytest.raises(ScenarioError):
        load_registry(project)
    scenario.unlink()
    scenario.write_bytes(data)
    (project / "faults/seeded/F01.json").unlink()
    with pytest.raises(ScenarioError):
        load_registry(project)


def test_unregistered_fixture(project: Path) -> None:
    path = project / SCENARIO
    path.write_text(path.read_text().replace("order-service@", "unregistered@"))
    with pytest.raises(ScenarioError, match="unregistered fixture"):
        load_registry(project)


def test_cli_list_and_validate(project: Path) -> None:
    runner = CliRunner()
    listing = runner.invoke(app, ["scenarios", "list", "--root", str(project)])
    assert listing.exit_code == 0, listing.output
    assert "F01\tnull-handling\tcorrectness" in listing.output
    valid = runner.invoke(app, ["validate", "--root", str(project), "--scenario", SCENARIO])
    assert valid.exit_code == 0, valid.output
    assert "Valid F01:" in valid.output
    invalid = runner.invoke(app, ["validate", "--root", str(project), "--scenario", "../secret"])
    assert invalid.exit_code == 2
    assert "Invalid scenario" in invalid.output
