"""Five rubric judges sharing strict output and citation validation."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from agentforge.core.artifacts import digest_bytes
from agentforge.core.schemas import (
    Digest,
    EvidenceBundle,
    JudgeResult,
    Text,
    Versioned,
)
from agentforge.core.trace import canonical_json
from agentforge.evaluation.rubrics import Rubric
from agentforge.judges.context import JudgeError, prepare_evidence
from agentforge.judges.prompts import prompt_for
from agentforge.providers.base import JudgeProvider, JudgeRequest, ProviderResponse


class JudgeEvaluation(Versioned):
    result: JudgeResult
    evidence_revision: Digest
    rubric_revision: Digest
    prompt_revision: Digest
    request_revision: Digest
    started_at: Text
    finished_at: Text
    usage: ProviderResponse


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise JudgeError("duplicate model output key")
        value[key] = item
    return value


def validate_result(
    response: ProviderResponse, request: JudgeRequest, evidence: EvidenceBundle
) -> JudgeResult:
    try:
        payload = json.loads(response.output_json, object_pairs_hook=_unique)
        result = JudgeResult.model_validate_json(canonical_json(payload))
    except (ValueError, TypeError, RecursionError):
        raise JudgeError("invalid structured judge output") from None
    if (
        result.run_id != request.run_id
        or result.dimension != request.dimension
        or result.prompt_version != request.prompt_version
        or result.judge_model != request.model
        or response.model != request.model
    ):
        raise JudgeError("judge response identity mismatch")
    refs = list(result.evidence)
    for finding in result.findings:
        refs.extend(finding.evidence)
    for ref in refs:
        if ref.kind == "event":
            valid = ref in evidence.events
        else:
            valid = any(
                ref.path == source.path
                and ref.revision == source.revision
                and source.start_line <= ref.start_line <= ref.end_line <= source.end_line
                for source in evidence.inspected_files
            )
        if not valid:
            raise JudgeError("ungrounded evidence citation")
    return result


def evaluate_judges(
    *,
    evidence: EvidenceBundle,
    files: Mapping[str, bytes],
    trace: bytes,
    rubric: Rubric,
    provider: JudgeProvider,
    model: str,
) -> tuple[JudgeEvaluation, ...]:
    """Evaluate all five criteria, failing explicitly on invalid/unavailable output.

    Providers are trusted installed code, not an OS sandbox. Only immutable strings
    reach their API; no collector, writable model, gateway or execution handle does.
    Model is an explicit caller-pinned provider/version identifier.
    """
    context = prepare_evidence(evidence, files=files, trace=trace)
    bundle = EvidenceBundle.model_validate_json(json.dumps(json.loads(context)["bundle"]))
    try:
        rubric = Rubric.model_validate_json(rubric.model_dump_json())
    except (ValueError, TypeError, AttributeError):
        raise JudgeError("invalid rubric") from None
    output_schema = canonical_json(JudgeResult.model_json_schema()).decode()
    evaluations = []
    for rule in rubric.dimensions:
        version, prompt = prompt_for(rule.dimension)
        request = JudgeRequest(
            run_id=bundle.run_id,
            dimension=rule.dimension,
            model=model,
            prompt_version=version,
            system_prompt=prompt,
            evidence_json=canonical_json(
                dict(evidence=json.loads(context), rubric=rubric.model_dump(mode="json"))
            ).decode(),
            output_schema_json=output_schema,
        )
        started = datetime.now(UTC).isoformat()
        try:
            raw = provider.complete(request)
            response = ProviderResponse.model_validate_json(
                canonical_json(raw.model_dump(mode="json"))
            )
        except Exception:
            # Never convert a failed provider call into a fabricated score or offline success.
            raise JudgeError("provider unavailable or invalid response") from None
        result = validate_result(response, request, bundle)
        evaluations.append(
            JudgeEvaluation(
                schema_version="1",
                result=result,
                evidence_revision=bundle.revision,
                rubric_revision=rubric.revision,
                prompt_revision=digest_bytes(prompt.encode()),
                request_revision=digest_bytes(canonical_json(request.model_dump(mode="json"))),
                started_at=started,
                finished_at=datetime.now(UTC).isoformat(),
                usage=response,
            )
        )
    return tuple(evaluations)
