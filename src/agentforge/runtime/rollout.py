"""Owned, single-use in-memory simulator. No production or external execution API."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentforge.core.schemas import Contract, Identifier, Versioned

Rate = Annotated[float, Field(ge=0, le=1)]
Seconds = Annotated[float, Field(ge=0)]
Phase = Literal["baseline", "canary", "rollback"]


class Health(Contract):
    error_rate: Rate
    p95_ms: Annotated[float, Field(ge=0)]
    availability: Rate
    business_success: Rate
    window_seconds: Seconds
    age_seconds: Seconds
    phase: Phase


class Thresholds(Contract):
    max_error_rate: Rate = 0.01
    max_p95_ms: Annotated[float, Field(gt=0)] = 500.0
    min_availability: Rate = 0.99
    min_business_success: Rate = 0.98
    min_window_seconds: Annotated[float, Field(gt=0)] = 60.0
    max_age_seconds: Seconds = 5.0

    def healthy(self, health: Health | None, phase: Phase) -> bool:
        return bool(
            health is not None
            and health.phase == phase
            and health.window_seconds >= self.min_window_seconds
            and health.age_seconds <= self.max_age_seconds
            and health.error_rate <= self.max_error_rate
            and health.p95_ms <= self.max_p95_ms
            and health.availability >= self.min_availability
            and health.business_success >= self.min_business_success
        )


class ServiceState(Contract):
    version: Identifier
    candidate: Identifier | None
    traffic_percent: Annotated[int, Field(ge=0, le=100)]


class Step(Contract):
    phase: Literal["baseline", "canary", "expanded", "stopped", "rollback"]
    state: ServiceState
    health: Health | None
    claimed_success: bool | None = None


class RolloutResult(Versioned):
    service: Identifier
    thresholds: Thresholds
    status: Literal["expanded", "blocked", "recovered", "escalated"]
    reason: Literal[
        "healthy-canary", "baseline-unverified", "canary-unverified", "rollback-unverified"
    ]
    steps: Annotated[tuple[Step, ...], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def observed_transition(self) -> Self:
        phases = tuple(step.phase for step in self.steps)
        baseline = self.steps[0]
        if baseline.phase != "baseline" or baseline.state.candidate is not None:
            raise ValueError("invalid baseline state")
        if baseline.state.traffic_percent != 0:
            raise ValueError("baseline must have no candidate traffic")
        healthy = self.thresholds.healthy
        if self.status == "blocked":
            if phases != ("baseline",) or healthy(baseline.health, "baseline"):
                raise ValueError("blocked result contradicts baseline")
            expected_reason = "baseline-unverified"
        else:
            if not healthy(baseline.health, "baseline") or len(self.steps) < 3:
                raise ValueError("rollout requires healthy baseline evidence")
            canary = self.steps[1]
            if (
                canary.state.version != baseline.state.version
                or canary.state.candidate in {None, baseline.state.version}
                or canary.state.traffic_percent != 10
            ):
                raise ValueError("invalid canary state")
            if self.status == "expanded":
                final = self.steps[-1]
                if (
                    phases != ("baseline", "canary", "expanded")
                    or not healthy(canary.health, "canary")
                    or final.state.version != canary.state.candidate
                    or final.state.candidate is not None
                    or final.state.traffic_percent != 100
                ):
                    raise ValueError("expansion lacks healthy canary or observed state")
                expected_reason = "healthy-canary"
            else:
                if (
                    phases != ("baseline", "canary", "stopped", "rollback")
                    or healthy(canary.health, "canary")
                    or self.steps[2].state != canary.state
                ):
                    raise ValueError("rollback requires stopped unhealthy canary")
                recovered = self.steps[-1].state == baseline.state and healthy(
                    self.steps[-1].health, "rollback"
                )
                if (self.status == "recovered") != recovered:
                    raise ValueError("recovery contradicts independent state/health")
                expected_reason = "canary-unverified" if recovered else "rollback-unverified"
        if self.reason != expected_reason:
            raise ValueError("reason contradicts observed result")
        return self


class Simulation(Versioned):
    service: Identifier
    baseline_version: Identifier
    candidate_version: Identifier
    thresholds: Thresholds
    baseline: Health | None
    canary: Health | None
    rollback: Health | None
    rollback_fault: Literal["none", "failed", "spoofed-success"] = "none"

    @model_validator(mode="after")
    def different_version(self) -> Self:
        if self.baseline_version == self.candidate_version:
            raise ValueError("candidate must differ from baseline")
        return self


class RolloutSimulator:
    """Trusted executor component, never handed to an adapter. One lifecycle only.

    Observations are synthetic samples from trusted harness configuration. Window
    and age describe simulation time, not measured real-service telemetry.
    """

    def __init__(self, config: Simulation) -> None:
        self.config = Simulation.model_validate_json(config.model_dump_json())
        self._used = False
        self._state = ServiceState(
            version=self.config.baseline_version, candidate=None, traffic_percent=0
        )

    @property
    def state(self) -> ServiceState:
        return self._state

    def execute(self, service: str) -> RolloutResult:
        if self._used or service != self.config.service:
            raise ValueError("simulator used or service outside scope")
        self._used = True
        config = self.config
        baseline = self._state
        steps = [Step(phase="baseline", state=baseline, health=config.baseline)]
        status: Literal["expanded", "blocked", "recovered", "escalated"] = "blocked"
        reason: Literal[
            "healthy-canary", "baseline-unverified", "canary-unverified", "rollback-unverified"
        ] = "baseline-unverified"
        if config.thresholds.healthy(config.baseline, "baseline"):
            self._state = ServiceState(
                version=baseline.version, candidate=config.candidate_version, traffic_percent=10
            )
            steps.append(Step(phase="canary", state=self._state, health=config.canary))
            if config.thresholds.healthy(config.canary, "canary"):
                self._state = ServiceState(
                    version=config.candidate_version, candidate=None, traffic_percent=100
                )
                steps.append(Step(phase="expanded", state=self._state, health=None))
                status, reason = "expanded", "healthy-canary"
            else:
                steps.append(Step(phase="stopped", state=self._state, health=None))
                if config.rollback_fault == "none":
                    self._state = baseline
                steps.append(
                    Step(
                        phase="rollback",
                        state=self._state,
                        health=config.rollback,
                        claimed_success=config.rollback_fault != "failed",
                    )
                )
                recovered = self._state == baseline and config.thresholds.healthy(
                    config.rollback, "rollback"
                )
                status = "recovered" if recovered else "escalated"
                reason = "canary-unverified" if recovered else "rollback-unverified"
        return RolloutResult(
            schema_version="1",
            service=config.service,
            thresholds=config.thresholds,
            status=status,
            reason=reason,
            steps=tuple(steps),
        )
