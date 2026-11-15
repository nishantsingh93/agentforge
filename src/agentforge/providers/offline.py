"""Explicit absence of semantic judgment; no credentials or network required."""

from agentforge.core.schemas import JudgeResult
from agentforge.providers.base import JudgeRequest, ProviderResponse


class OfflineProvider:
    def complete(self, request: JudgeRequest) -> ProviderResponse:
        if request.model != "offline":
            raise ValueError("offline provider requires the offline model")
        result = JudgeResult(
            schema_version="1",
            run_id=request.run_id,
            dimension=request.dimension,
            score=None,
            status="UNKNOWN",
            findings=(),
            evidence=(),
            missing_evidence=("Semantic model review unavailable in offline mode",),
            confidence=None,
            judge_model="offline",
            prompt_version=request.prompt_version,
        )
        return ProviderResponse(
            output_json=result.model_dump_json(),
            model="offline",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        )
