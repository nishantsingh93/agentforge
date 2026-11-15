"""Strict synthetic benchmark records and label-free judge inputs."""

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import model_validator

from agentforge.core.artifacts import digest_bytes
from agentforge.core.schemas import (
    Contract,
    Digest,
    Dimension,
    EvidenceBundle,
    FileRef,
    Identifier,
    Text,
    Versioned,
)
from agentforge.core.trace import canonical_json
from agentforge.evaluation.rubrics import Rubric
from agentforge.judges.context import prepare_evidence
from agentforge.judges.prompts import prompt_for
from agentforge.providers.base import JudgeRequest

Status = Literal["PASS", "REVISE", "FAIL", "UNKNOWN"]
Split = Literal["development", "holdout"]
Severity = Literal["none", "low", "medium", "high", "critical"]
MAX_BYTES = 8_388_608
MAX_RECORDS = 1000


class Case(Versioned):
    case_id: Identifier
    family: Identifier
    split: Split
    dimension: Dimension
    severity: Severity
    observations: Text
    provenance: Literal["authored_synthetic"]

    @property
    def revision(self) -> str:
        return digest_bytes(canonical_json(self.model_dump(mode="json")))


class Review(Contract):
    reviewer: Identifier
    status: Status
    rationale: Text


class Label(Versioned):
    case_id: Identifier
    case_revision: Digest
    status: Status
    rationale: Text
    review_status: Literal["provisional", "adjudicated"]
    reviews: tuple[Review, ...]
    adjudicator: Identifier | None
    adjudication: Text | None

    @model_validator(mode="after")
    def review_provenance(self) -> Self:
        names = [r.reviewer for r in self.reviews]
        if len(names) != len(set(names)):
            raise ValueError("duplicate reviewer")
        if self.review_status == "adjudicated":
            if len(names) < 2:
                raise ValueError("two independent reviews required")
            if any(r.status != self.status for r in self.reviews):
                if not self.adjudicator or self.adjudicator in names or not self.adjudication:
                    raise ValueError("disagreement requires independent adjudication")
        return self


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def load_jsonl[T: Contract](path: Path, model: type[T]) -> tuple[T, ...]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("benchmark file exceeds size limit")
    lines = raw.splitlines()
    if not lines or len(lines) > MAX_RECORDS or any(not line.strip() for line in lines):
        raise ValueError("invalid benchmark record count or blank record")
    return tuple(
        model.model_validate_json(canonical_json(json.loads(line, object_pairs_hook=_unique)))
        for line in lines
    )


def load_cases(path: Path) -> tuple[Case, ...]:
    cases = load_jsonl(path, Case)
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case ID")
    families: dict[str, set[str]] = {}
    for case in cases:
        families.setdefault(case.family, set()).add(case.split)
    if any(len(splits) != 1 for splits in families.values()):
        raise ValueError("case family leaks across splits")
    return cases


def validate_labels(cases: tuple[Case, ...], labels: tuple[Label, ...]) -> None:
    if len({label.case_id for label in labels}) != len(labels):
        raise ValueError("duplicate label ID")
    indexed = {label.case_id: label for label in labels}
    if set(indexed) != {c.case_id for c in cases}:
        raise ValueError("labels must cover exactly the selected cases")
    if any(indexed[c.case_id].case_revision != c.revision for c in cases):
        raise ValueError("stale label revision")


def request_for(case: Case, rubric: Rubric, model: str) -> tuple[JudgeRequest, EvidenceBundle]:
    """No labels, severity, split, family or rationale cross the provider boundary.

    The observation file is an authored vignette, NOT an observed execution trace.
    Its hash commits to the synthetic input, not to real-world authenticity.
    """
    from agentforge.core.schemas import JudgeResult

    content = (
        "Authored synthetic benchmark vignette; no real execution is claimed.\n"
        + case.observations
        + "\n"
    ).encode()
    ref = FileRef(
        kind="file",
        path="observations.txt",
        revision=digest_bytes(content),
        start_line=1,
        end_line=len(content.decode().splitlines()),
    )
    body = dict(
        schema_version="1",
        run_id=case.case_id,
        inspected_files=[ref.model_dump()],
        diff="",
        commands=[],
        snapshots=[],
        events=[],
        redacted=True,
        redaction_notes=["Owned synthetic text; no production data."],
    )
    bundle = EvidenceBundle.model_validate_json(
        canonical_json(dict(body, revision=digest_bytes(canonical_json(body))))
    )
    context = prepare_evidence(bundle, files={"observations.txt": content}, trace=b"")
    version, prompt = prompt_for(case.dimension)
    request = JudgeRequest(
        run_id=case.case_id,
        dimension=case.dimension,
        model=model,
        prompt_version=version,
        system_prompt=prompt,
        evidence_json=canonical_json(
            dict(evidence=json.loads(context), rubric=rubric.model_dump(mode="json"))
        ).decode(),
        output_schema_json=canonical_json(JudgeResult.model_json_schema()).decode(),
    )
    return request, bundle


def request_revision(request: JudgeRequest) -> str:
    return digest_bytes(canonical_json(request.model_dump(mode="json")))


class BlindInput(Versioned):
    case_id: Identifier
    request_revision: Digest
    request: JudgeRequest
