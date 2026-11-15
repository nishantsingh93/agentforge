"""Immutable data-only boundary for trusted provider implementations."""

from typing import Annotated, Protocol

from pydantic import Field

from agentforge.core.schemas import Contract, Dimension, Identifier, Text


class JudgeRequest(Contract):
    run_id: Identifier
    dimension: Dimension
    model: Text
    prompt_version: Identifier
    system_prompt: str
    evidence_json: str
    output_schema_json: str


class ProviderResponse(Contract):
    output_json: Annotated[str, Field(max_length=262144)]
    model: Text
    input_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    cost_usd: Annotated[float, Field(ge=0)] | None


class JudgeProvider(Protocol):
    def complete(self, request: JudgeRequest) -> ProviderResponse:
        """Return JSON and usage only. No tool or executor interface is supplied."""
        ...
