"""Pure adapter contracts. No executor or collector capabilities are supplied."""

from typing import Annotated, Protocol, Self

from pydantic import Field, model_validator

from agentforge.core.schemas import ActionRequest, Identifier, Text, Versioned


class AdapterTask(Versioned):
    task_id: Identifier
    scenario_id: Identifier
    instruction: Text
    source: Annotated[str, Field(max_length=1_000_000)]


class AdapterPlan(Versioned):
    requests: Annotated[tuple[ActionRequest, ...], Field(max_length=32)]
    claim: Text

    @model_validator(mode="after")
    def unique_requests(self) -> Self:
        for values in (
            [request.action_id for request in self.requests],
            [request.idempotency_key for request in self.requests],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate adapter request identifiers")
        return self


class AgentAdapter(Protocol):
    def propose(self, task: AdapterTask) -> AdapterPlan: ...
