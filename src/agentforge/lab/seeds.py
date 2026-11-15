"""Pinned data-only fault injection into disposable immutable snapshots."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from agentforge.core.artifacts import digest_bytes
from agentforge.core.fixtures import FixtureFile, FixtureSnapshot, read_project_file
from agentforge.core.scenario import RegisteredScenario, _unique_json, load_registry
from agentforge.core.schemas import Contract, Digest, Identifier, Versioned, relative_path
from agentforge.core.trace import canonical_json
from agentforge.evaluation.outcome import OutcomeProfile
from agentforge.runtime.rollout import Simulation
from agentforge.sandbox.runner import encode_snapshot


class Replacement(Contract):
    path: str
    before: Digest | None
    content: Annotated[str, Field(max_length=1_000_000)]

    @model_validator(mode="after")
    def canonical(self) -> Self:
        relative_path(self.path)
        return self


class Variant(Contract):
    name: Identifier
    simulation: Simulation


class FaultDefinition(Versioned):
    scenario_id: Identifier
    replacements: Annotated[tuple[Replacement, ...], Field(max_length=64)]
    simulation: Simulation | None = None
    variants: tuple[Variant, ...] = ()

    @model_validator(mode="after")
    def unique(self) -> Self:
        paths = [r.path for r in self.replacements]
        names = [v.name for v in self.variants]
        if len(paths) != len(set(paths)) or len(names) != len(set(names)) or "default" in names:
            raise ValueError("duplicate replacement or variant")
        if not self.replacements and self.simulation is None:
            raise ValueError("fault must change fixture or simulation")
        if self.variants and self.simulation is None:
            raise ValueError("variants require default simulation")
        return self


class SeedProfile(Versioned):
    fault_revision: Digest
    outcome: OutcomeProfile


@dataclass(frozen=True)
class Seed:
    registered: RegisteredScenario
    fault: FaultDefinition
    profile: OutcomeProfile


@dataclass(frozen=True)
class PreparedScenario:
    seed: Seed
    snapshot: FixtureSnapshot
    simulation: Simulation | None


class SeedError(ValueError):
    """Missing, modified or unsafe lab data. No fixture is executed."""


def _json(data: bytes) -> str:
    return json.dumps(json.loads(data, object_pairs_hook=_unique_json), allow_nan=False)


def load_seeds(root: Path) -> tuple[Seed, ...]:
    """Registered scenarios only; fixed profile paths, no dynamic code loading."""
    try:
        seeds = []
        for registered in load_registry(root):
            scenario = registered.scenario
            profile = SeedProfile.model_validate_json(
                _json(read_project_file(root, f"scenarios/profiles/{scenario.id}.json"))
            )
            fault = FaultDefinition.model_validate_json(_json(registered.fault))
            if fault.scenario_id != scenario.id or profile.outcome.scenario_id != scenario.id:
                raise SeedError("seed scenario identity mismatch")
            if profile.fault_revision != digest_bytes(registered.fault):
                raise SeedError("fault revision mismatch")
            if profile.outcome.scenario_revision != digest_bytes(
                canonical_json(scenario.model_dump(mode="json"))
            ):
                raise SeedError("scenario revision mismatch")
            ids = {oracle.oracle_id for oracle in profile.outcome.oracles}
            if (
                not (set(scenario.expected) | set(scenario.forbidden) | set(scenario.oracles))
                <= ids
            ):
                raise SeedError("uncovered scenario expectations")
            seed = Seed(registered, fault, profile.outcome)
            prepare(seed)  # Validate replacement preimages and bounded output now.
            seeds.append(seed)
        return tuple(seeds)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        raise SeedError("invalid seeded scenario data") from error


def prepare(seed: Seed, variant: str = "default") -> PreparedScenario:
    """Pure setup: no subprocess, file writes, imports or mutable global state.

    This is fixture construction before an agent run, not an agent edit API.
    The caller supplies the resulting snapshot to the existing sandbox/gateway.
    """
    fault = FaultDefinition.model_validate_json(seed.fault.model_dump_json())
    base = seed.registered.fixture
    encode_snapshot(base)
    files = {file.path: file.content for file in base.files}
    for replacement in fault.replacements:
        current = files.get(replacement.path)
        actual = None if current is None else digest_bytes(current)
        if actual != replacement.before:
            raise SeedError("replacement preimage mismatch")
        content = replacement.content.encode()
        if current == content:
            raise SeedError("fault replacement is a no-op")
        files[replacement.path] = content
    entries = tuple(FixtureFile(path, content) for path, content in sorted(files.items()))
    manifest = [(entry.path, hashlib.sha256(entry.content).hexdigest()) for entry in entries]
    snapshot = FixtureSnapshot(
        digest_bytes(json.dumps(manifest, separators=(",", ":")).encode()), entries
    )
    encode_snapshot(snapshot)
    simulation = fault.simulation
    if variant != "default":
        matches = [item.simulation for item in fault.variants if item.name == variant]
        if not matches:
            raise SeedError("unknown simulation variant")
        simulation = matches[0]
    return PreparedScenario(seed, snapshot, simulation)


@contextmanager
def scenario_session(seed: Seed, variant: str = "default") -> Iterator[PreparedScenario]:
    """Each session owns fresh data. No host resources exist to leak on teardown.

    Container lifetimes remain the responsibility of the existing SandboxRunner.
    """
    yield prepare(seed, variant)
