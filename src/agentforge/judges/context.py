"""Verify supplied collector artifacts and freeze them as a data-only snapshot."""

from collections.abc import Mapping

from agentforge.core.artifacts import digest_bytes
from agentforge.core.schemas import EventRef, EvidenceBundle
from agentforge.core.trace import canonical_json, replay_trace

MAX_CONTEXT_BYTES = 8_388_608


class JudgeError(ValueError):
    """Invalid evidence, provider output or unavailable provider; no raw content exposed."""


def prepare_evidence(evidence: EvidenceBundle, *, files: Mapping[str, bytes], trace: bytes) -> str:
    """Caller supplies sanitized collector material, not arbitrary host paths.

    Hashes detect inconsistency, not a malicious caller replacing the entire run.
    Complete trace and file objects are required; absent evidence is not invented.
    """
    try:
        bundle = EvidenceBundle.model_validate_json(evidence.model_dump_json())
        if bundle.revision != digest_bytes(
            canonical_json(bundle.model_dump(mode="json", exclude={"revision"}))
        ):
            raise JudgeError("bundle revision mismatch")
        if len(trace) + sum(len(content) for content in files.values()) > MAX_CONTEXT_BYTES:
            raise JudgeError("evidence exceeds size limit")
        records = replay_trace(trace)
        refs = tuple(
            EventRef(kind="event", event_id=r.event.event_id, revision=r.revision) for r in records
        )
        if refs != bundle.events or any(r.event.run_id != bundle.run_id for r in records):
            raise JudgeError("trace does not match bundle")
        observed = tuple(r.event.tool_result for r in records if r.event.tool_result is not None)
        if observed != bundle.commands:
            raise JudgeError("command observations do not match trace")
        if len({c.command_id for c in bundle.commands}) != len(bundle.commands):
            raise JudgeError("duplicate command identity")
        if len({f.path for f in bundle.inspected_files}) != len(bundle.inspected_files):
            raise JudgeError("duplicate file identity")
        if set(files) != {f.path for f in bundle.inspected_files}:
            raise JudgeError("file set does not match bundle")
        material = []
        for ref in bundle.inspected_files:
            content = files[ref.path]
            if not isinstance(content, bytes) or digest_bytes(content) != ref.revision:
                raise JudgeError("file revision mismatch")
            text = content.decode("utf-8")
            if ref.end_line > max(1, len(text.splitlines())):
                raise JudgeError("file range outside artifact")
            material.append(dict(reference=ref.model_dump(mode="json"), content=text))
        for snapshot in bundle.snapshots:
            if digest_bytes(canonical_json(snapshot.state)) != snapshot.revision:
                raise JudgeError("snapshot revision mismatch")
        serialized = canonical_json(
            dict(
                bundle=bundle.model_dump(mode="json"),
                files=material,
                trace=[r.model_dump(mode="json") for r in records],
            )
        )
        if len(serialized) > MAX_CONTEXT_BYTES:
            raise JudgeError("evidence exceeds size limit")
        return serialized.decode()
    except JudgeError:
        raise
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise JudgeError("invalid evidence material") from None
