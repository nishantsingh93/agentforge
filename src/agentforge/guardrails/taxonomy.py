"""Version-one risk vocabulary and trusted policy context."""

from enum import IntEnum
from typing import Self

from pydantic import model_validator

from agentforge.core.schemas import (
    CheckName,
    Environment,
    Identifier,
    Versioned,
    relative_path,
)


class RiskTier(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class PolicyContext(Versioned):
    run_id: Identifier
    scenario_id: Identifier
    environment: Environment
    allowed_files: tuple[str, ...]
    allowed_services: tuple[Identifier, ...]
    allowed_checks: tuple[CheckName, ...]
    protected_paths: tuple[str, ...]
    minimum_risk: RiskTier
    isolation_verified: bool | None
    tests_passed: bool | None
    baseline_healthy: bool | None
    rollback_ready: bool | None

    @model_validator(mode="after")
    def canonical_scopes(self) -> Self:
        for path in (*self.allowed_files, *self.protected_paths):
            relative_path(path)
        for entries in (
            self.allowed_files,
            self.allowed_services,
            self.allowed_checks,
            self.protected_paths,
        ):
            if len(entries) != len(set(entries)):
                raise ValueError("duplicate trusted scope")
        return self
