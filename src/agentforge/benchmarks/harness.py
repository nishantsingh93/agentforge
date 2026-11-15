"""Collect data-only predictions and validate them independently of reference labels."""

from time import perf_counter
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentforge.benchmarks.data import Case, request_for, request_revision
from agentforge.core.schemas import Digest, Identifier, Text, Versioned
from agentforge.core.trace import canonical_json
from agentforge.evaluation.rubrics import Rubric
from agentforge.providers.base import JudgeProvider, ProviderResponse


class Prediction(Versioned):
    case_id: Identifier
    request_revision: Digest
    model: Text
    response: ProviderResponse | None
    elapsed_seconds: Annotated[float, Field(ge=0)]
    error: Literal["provider_error"] | None

    @model_validator(mode="after")
    def consistent_response(self) -> Self:
        if (self.response is None) != (self.error is not None):
            raise ValueError("prediction requires a response or an explicit error")
        return self


def predict(
    cases: tuple[Case, ...], rubric: Rubric, provider: JudgeProvider, model: str
) -> tuple[Prediction, ...]:
    """Trusted provider code receives frozen requests only, never reference labels.

    Exceptions are sanitized. Invalid outputs remain recorded for scoring as invalid,
    rather than disappearing from denominators. No commands, actions or retries.
    """
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("expected nonempty unique cases")
    predictions = []
    for case in cases:
        request, _ = request_for(case, rubric, model)
        started = perf_counter()
        response = None
        error: Literal["provider_error"] | None = None
        try:
            raw = provider.complete(request)
            response = ProviderResponse.model_validate_json(canonical_json(raw.model_dump()))
        except Exception:
            error = "provider_error"
        predictions.append(
            Prediction(
                schema_version="1",
                case_id=case.case_id,
                request_revision=request_revision(request),
                model=model,
                response=response,
                elapsed_seconds=perf_counter() - started,
                error=error,
            )
        )
    return tuple(predictions)
