"""Bounded explicit rubric registry. YAML is data, never executable instructions."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import Field, model_validator

from agentforge.core.fixtures import read_project_file
from agentforge.core.scenario import MAX_SCENARIO_BYTES, RestrictedLoader
from agentforge.core.schemas import (
    DIMENSIONS,
    CheckName,
    Contract,
    Dimension,
    Identifier,
    Score,
    Versioned,
)
from agentforge.core.trace import canonical_json


class DimensionRule(Contract):
    dimension: Dimension
    weight: Annotated[int, Field(ge=1, le=100)]
    minimum: Score


class Rubric(Versioned):
    rubric_id: Identifier
    dimensions: Annotated[tuple[DimensionRule, ...], Field(min_length=5, max_length=5)]
    pass_threshold: Score
    revise_threshold: Score
    required_checks: Annotated[tuple[CheckName, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def coherent_rules(self) -> Self:
        if {rule.dimension for rule in self.dimensions} != set(DIMENSIONS):
            raise ValueError("each rubric dimension is required exactly once")
        if sum(rule.weight for rule in self.dimensions) != 100:
            raise ValueError("weights must sum to 100")
        if self.revise_threshold >= self.pass_threshold:
            raise ValueError("revise threshold must be below pass threshold")
        if len(set(self.required_checks)) != len(self.required_checks):
            raise ValueError("duplicate required checks")
        return self

    @property
    def revision(self) -> str:
        return "sha256:" + hashlib.sha256(canonical_json(self.model_dump(mode="json"))).hexdigest()


class RubricError(ValueError):
    """Invalid, unregistered or unavailable rubric configuration."""


def parse_rubric(data: bytes) -> Rubric:
    if len(data) > MAX_SCENARIO_BYTES:
        raise RubricError("rubric exceeds size limit")
    try:
        decoded = yaml.load(data.decode("utf-8"), Loader=RestrictedLoader)
        return Rubric.model_validate_json(json.dumps(decoded, allow_nan=False))
    except (UnicodeError, yaml.YAMLError, TypeError, ValueError, RecursionError):
        raise RubricError("invalid rubric configuration") from None


def load_rubric(root: Path, rubric_id: str = "production_patch_v1") -> Rubric:
    """Load only the owned registered file; callers can parse custom bytes explicitly."""
    if rubric_id != "production_patch_v1":
        raise RubricError("unregistered rubric")
    try:
        rubric = parse_rubric(
            read_project_file(root, "rubrics/production_patch_v1.yaml", MAX_SCENARIO_BYTES)
        )
    except (OSError, ValueError):
        raise RubricError("cannot load registered rubric") from None
    if rubric.rubric_id != rubric_id:
        raise RubricError("registered rubric ID mismatch")
    return rubric
