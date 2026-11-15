"""Sanitized append-only traces and read-only hash-chain verification."""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue, ValidationError

from agentforge.core.artifacts import digest_bytes
from agentforge.core.redaction import Redactor
from agentforge.core.schemas import (
    ActionRequest,
    Contract,
    Digest,
    PolicyDecision,
    ToolResult,
    TraceEvent,
)

MAX_TRACE_BYTES = 67_108_864
MAX_RECORD_BYTES = 2_097_152
MAX_RECORDS = 10_000


class TraceError(ValueError):
    """Missing, malformed or inconsistent trace evidence."""


class TraceRecord(Contract):
    schema_version: Literal["1"]
    previous: Digest | None
    revision: Digest
    event: TraceEvent
    redacted: bool
    redaction_rules: tuple[str, ...]

    def expected_revision(self) -> str:
        body = self.model_dump(mode="json", exclude={"revision"})
        return digest_bytes(canonical_json(body))


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TraceError("duplicate JSON key in trace")
        result[key] = value
    return result


def replay_trace(data: bytes, expected_head: str | None = None) -> tuple[TraceRecord, ...]:
    """Verify complete JSONL. A known external head additionally detects truncation."""
    if len(data) > MAX_TRACE_BYTES or (data and not data.endswith(b"\n")):
        raise TraceError("trace too large or incomplete")
    records: list[TraceRecord] = []
    seen: set[str] = set()
    head: str | None = None
    run_id: str | None = None
    for raw_line in BytesIO(data):
        if len(records) >= MAX_RECORDS:
            raise TraceError("too many trace records")
        line = raw_line[:-1]
        if not line or len(line) > MAX_RECORD_BYTES:
            raise TraceError("invalid trace record size")
        try:
            payload = json.loads(line, object_pairs_hook=_unique_object)
            record = TraceRecord.model_validate_json(canonical_json(payload))
        except (ValueError, TypeError, RecursionError, ValidationError):
            raise TraceError("malformed trace record") from None
        event = record.event
        if record.previous != head or record.expected_revision() != record.revision:
            raise TraceError("trace hash chain mismatch")
        if event.sequence != len(records) + 1 or event.event_id in seen:
            raise TraceError("trace sequence or event ID mismatch")
        if run_id is not None and event.run_id != run_id:
            raise TraceError("trace run ID mismatch")
        if event.parent_id is not None and event.parent_id not in seen:
            raise TraceError("trace parent must reference an earlier event")
        if record.redacted != bool(record.redaction_rules):
            raise TraceError("redaction metadata mismatch")
        seen.add(event.event_id)
        run_id = event.run_id
        head = record.revision
        records.append(record)
    if expected_head is not None and head != expected_head:
        raise TraceError("trace does not match trusted head")
    return tuple(records)


class TraceCollector:
    """Single writer. Only trusted executor wiring may call observed_result.

    A write failure poisons the writer: partial tails must never be continued.
    Python methods are not a security boundary against malicious in-process code.
    """

    def __init__(self, directory: Path, run_id: str, redactor: Redactor) -> None:
        self._redactor = redactor
        safe = redactor.sanitize(run_id)
        if (
            safe.value != run_id
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id) is None
        ):
            raise TraceError("invalid or sensitive run identifier")
        self.run_id = run_id
        self._records: list[TraceRecord] = []
        self._failed = False
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._fd = os.open(
                "trace.jsonl",
                os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        if self._fd < 0 or self._failed:
            raise TraceError("trace writer closed or failed")
        persisted = os.pread(self._fd, MAX_TRACE_BYTES + 1, 0)
        replayed = replay_trace(persisted, self._records[-1].revision if self._records else None)
        if len(replayed) != len(self._records):
            raise TraceError("persisted trace differs from writer state")
        # Return validated copies: nested JSON fields in contracts can be mutable.
        return tuple(TraceRecord.model_validate_json(r.model_dump_json()) for r in self._records)

    def agent_claim(self, claim: str, *, parent_id: str | None = None) -> TraceRecord:
        return self._append("agent", claim=claim, parent_id=parent_id)

    def runner_observation(self, note: str, *, parent_id: str | None = None) -> TraceRecord:
        """Trusted runtime audit note, never an agent assertion of execution."""
        return self._append("runner", claim=note, parent_id=parent_id)

    def observed_result(self, result: ToolResult, *, parent_id: str | None = None) -> TraceRecord:
        return self._append("executor", result=result, parent_id=parent_id)

    def proposed_action(
        self, action: ActionRequest, *, parent_id: str | None = None
    ) -> TraceRecord:
        return self._append("agent", action=action, parent_id=parent_id)

    def policy_decision(
        self, action: ActionRequest, decision: PolicyDecision, *, parent_id: str | None = None
    ) -> TraceRecord:
        return self._append("gateway", action=action, decision=decision, parent_id=parent_id)

    def _append(
        self,
        actor: str,
        *,
        claim: str | None = None,
        result: ToolResult | None = None,
        action: ActionRequest | None = None,
        decision: PolicyDecision | None = None,
        parent_id: str | None = None,
    ) -> TraceRecord:
        if self._fd < 0 or self._failed:
            raise TraceError("trace writer closed or failed")
        _ = self.records  # Verify the persisted prefix before extending it.
        payload: dict[str, JsonValue] = dict(
            schema_version="1",
            event_id="event-" + uuid.uuid4().hex,
            run_id=self.run_id,
            sequence=len(self._records) + 1,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            actor=actor,
            parent_id=parent_id,
            action=action.model_dump(mode="json") if action is not None else None,
            policy_decision=decision.model_dump(mode="json") if decision is not None else None,
            tool_result=result.model_dump(mode="json") if result is not None else None,
            evidence=[],
            claim=claim,
        )
        sanitized = self._redactor.sanitize(payload)
        try:
            event = TraceEvent.model_validate_json(canonical_json(sanitized.value))
            # Structural provenance must survive redaction exactly.
            for key in ("event_id", "run_id", "sequence", "timestamp", "actor", "parent_id"):
                if getattr(event, key) != payload[key]:
                    raise TraceError("redaction changed trace provenance")
            body = dict(
                schema_version="1",
                previous=self._records[-1].revision if self._records else None,
                event=event.model_dump(mode="json"),
                redacted=bool(sanitized.rules),
                redaction_rules=sanitized.rules,
            )
            record = TraceRecord.model_validate_json(
                canonical_json(dict(body, revision=digest_bytes(canonical_json(body))))
            )
            data = canonical_json(record.model_dump(mode="json")) + b"\n"
            replay_trace(
                b"".join(canonical_json(r.model_dump(mode="json")) + b"\n" for r in self._records)
                + data
            )
        except (ValueError, TypeError, RecursionError):
            raise TraceError("sanitized trace contract invalid") from None
        try:
            if os.write(self._fd, data) != len(data):
                raise OSError("incomplete trace append")
            os.fsync(self._fd)
        except OSError:
            self._failed = True
            raise TraceError("trace append failed") from None
        self._records.append(record)
        return TraceRecord.model_validate_json(record.model_dump_json())
