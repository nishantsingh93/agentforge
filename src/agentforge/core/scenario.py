"""Explicit scenario registry and restricted YAML loading."""

import json
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import Field, ValidationError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node

from agentforge.core.fixtures import (
    FixtureError,
    FixtureSnapshot,
    read_project_file,
    snapshot_fixture,
)
from agentforge.core.schemas import Contract, Scenario, relative_path

MAX_SCENARIO_BYTES = 65_536
MAX_YAML_DEPTH = 32
MAX_YAML_NODES = 4096


class ScenarioError(ValueError):
    """Invalid or unavailable registry/scenario data."""


class RestrictedLoader(yaml.SafeLoader):
    """Safe YAML with no aliases, duplicate keys, merges or complex keys."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.depth = 0
        self.nodes = 0

    def compose_node(self, parent: Node | None, index: Any) -> Node:
        if self.check_event(AliasEvent):
            raise ScenarioError("YAML aliases are not supported")
        self.depth += 1
        self.nodes += 1
        try:
            if self.depth > MAX_YAML_DEPTH or self.nodes > MAX_YAML_NODES:
                raise ScenarioError("YAML structure exceeds limits")
            node = super().compose_node(parent, index)
            if node is None:
                raise ScenarioError("expected a YAML node")
            return node
        finally:
            self.depth -= 1

    def construct_mapping(self, node: Node, deep: bool = False) -> dict[Hashable, Any]:
        if not isinstance(node, MappingNode):
            raise ScenarioError("expected a YAML mapping")
        result: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ScenarioError("YAML keys must be strings")
            if key in result:
                raise ScenarioError(f"duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse_scenario(data: bytes) -> Scenario:
    """Parse a single bounded YAML document and validate the strict wire schema."""
    if len(data) > MAX_SCENARIO_BYTES:
        raise ScenarioError("scenario exceeds size limit")
    try:
        decoded = yaml.load(data.decode("utf-8"), Loader=RestrictedLoader)
        wire = json.dumps(decoded, allow_nan=False)
        return Scenario.model_validate_json(wire)
    except (UnicodeError, yaml.YAMLError, TypeError, ValueError) as error:
        raise ScenarioError(f"invalid scenario: {error}") from error


class FixtureSpec(Contract):
    reference: Annotated[str, Field(pattern=r"^[a-z0-9-]+@sha256:[a-f0-9]{64}$")]
    directory: str


class RegistrySpec(Contract):
    schema_version: Literal["1"]
    scenarios: Annotated[tuple[str, ...], Field(min_length=1, max_length=256)]
    fixtures: Annotated[tuple[FixtureSpec, ...], Field(min_length=1, max_length=256)]


@dataclass(frozen=True)
class RegisteredScenario:
    source: str
    scenario: Scenario
    fixture: FixtureSnapshot
    fault: bytes


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioError(f"duplicate registry key: {key}")
        result[key] = value
    return result


def load_registry(root: Path) -> tuple[RegisteredScenario, ...]:
    """Resolve only explicitly listed scenarios and digest-pinned fixture trees."""
    try:
        raw = read_project_file(root, "scenarios/registry.json", MAX_SCENARIO_BYTES)
        decoded = json.loads(raw, object_pairs_hook=_unique_json)
        registry = RegistrySpec.model_validate_json(json.dumps(decoded, allow_nan=False))
        if len(set(registry.scenarios)) != len(registry.scenarios):
            raise ScenarioError("duplicate scenario path")
        fixtures: dict[str, FixtureSnapshot] = {}
        total_bytes = 0
        for spec in registry.fixtures:
            if spec.reference in fixtures:
                raise ScenarioError("duplicate fixture reference")
            snapshot = snapshot_fixture(root, spec.directory)
            total_bytes += sum(len(file.content) for file in snapshot.files)
            if total_bytes > 16_777_216:
                raise ScenarioError("registry fixtures exceed total size limit")
            if snapshot.digest != spec.reference.split("@", 1)[1]:
                raise ScenarioError(f"fixture digest mismatch: {spec.reference}")
            fixtures[spec.reference] = snapshot
        entries: list[RegisteredScenario] = []
        ids: set[str] = set()
        for path in registry.scenarios:
            relative_path(path)
            if not path.startswith("scenarios/") or Path(path).suffix not in {".yaml", ".yml"}:
                raise ScenarioError("scenario path must be a YAML file under scenarios/")
            scenario = parse_scenario(read_project_file(root, path, MAX_SCENARIO_BYTES))
            if scenario.id in ids:
                raise ScenarioError(f"duplicate scenario ID: {scenario.id}")
            ids.add(scenario.id)
            if scenario.fixture not in fixtures:
                raise ScenarioError(f"unregistered fixture: {scenario.fixture}")
            if not scenario.fault.ref.startswith("faults/"):
                raise ScenarioError("fault must be under faults/")
            fault = read_project_file(root, scenario.fault.ref)
            entries.append(RegisteredScenario(path, scenario, fixtures[scenario.fixture], fault))
        return tuple(sorted(entries, key=lambda entry: entry.scenario.id))
    except (
        OSError,
        UnicodeError,
        ValueError,
        RecursionError,
        FixtureError,
        ValidationError,
    ) as error:
        raise ScenarioError(str(error)) from error


def validate_registered(root: Path, relative: str) -> RegisteredScenario:
    """Validate the registry and select one of its explicitly approved paths."""
    relative_path(relative)
    for entry in load_registry(root):
        if entry.source == relative:
            return entry
    raise ScenarioError("scenario is not listed in scenarios/registry.json")
