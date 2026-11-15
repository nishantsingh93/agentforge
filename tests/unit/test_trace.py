"""Trace provenance, sanitization, persistence and replay regressions."""

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.core.artifacts import digest_bytes
from agentforge.core.redaction import Redactor
from agentforge.core.trace import TraceCollector, TraceError, canonical_json, replay_trace


def record(sequence: int = 1, previous: str | None = None, **changes: Any) -> dict[str, Any]:
    event = {
        "schema_version": "1",
        "event_id": f"event-{sequence}",
        "run_id": "run-1",
        "sequence": sequence,
        "timestamp": "2026-11-09T12:00:00Z",
        "actor": "agent",
        "parent_id": None,
        "action": None,
        "policy_decision": None,
        "tool_result": None,
        "evidence": [],
        "claim": "I claim tests passed; this is not execution evidence",
    }
    event.update(changes)
    body: dict[str, Any] = {
        "schema_version": "1",
        "previous": previous,
        "event": event,
        "redacted": False,
        "redaction_rules": [],
    }
    return dict(body, revision=digest_bytes(canonical_json(body)))


def encoded(*records: dict[str, Any]) -> bytes:
    return b"".join(canonical_json(item) + b"\n" for item in records)


def test_replay_hash_chain_with_actual_failing_result() -> None:
    first = record()
    second = record(
        2,
        first["revision"],
        actor="executor",
        parent_id="event-1",
        claim=None,
        tool_result={
            "command_id": "command-1",
            "check": "unit_tests",
            "status": "completed",
            "exit_code": 1,
            "stdout": "tests failed",
            "stderr": "",
            "duration_seconds": 0.1,
        },
    )
    replay = replay_trace(encoded(first, second), expected_head=second["revision"])
    assert replay[0].event.tool_result is None
    assert replay[1].event.tool_result is not None
    assert replay[1].event.tool_result.exit_code == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 2},
        {"parent_id": "unknown"},
        {
            "actor": "agent",
            "tool_result": {
                "command_id": "fake",
                "check": None,
                "status": "completed",
                "exit_code": 0,
                "stdout": "fake success",
                "stderr": "",
                "duration_seconds": 0.0,
            },
        },
    ],
)
def test_bad_provenance_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(TraceError):
        replay_trace(encoded(record(**changes)))


def test_tamper_and_truncation_rejected() -> None:
    first = record()
    second = record(2, first["revision"])
    with pytest.raises(TraceError, match="trusted head"):
        replay_trace(encoded(first), expected_head=second["revision"])
    second["event"]["claim"] = "rewritten"
    with pytest.raises(TraceError, match="hash"):
        replay_trace(encoded(first, second))
    with pytest.raises(TraceError, match="incomplete"):
        replay_trace(encoded(first)[:-1])


def test_cross_run_and_duplicate_ids_rejected() -> None:
    first = record()
    for changes in ({"run_id": "other"}, {"event_id": "event-1"}):
        second = record(2, first["revision"], **changes)
        with pytest.raises(TraceError):
            replay_trace(encoded(first, second))


def test_unknown_version_duplicate_keys_and_deep_json_rejected() -> None:
    body = record()
    body["schema_version"] = "2"
    for payload in (encoded(body), b'{"a":1,"a":2}\n', b"[" * 2000 + b"0" + b"]" * 2000 + b"\n"):
        with pytest.raises(TraceError):
            replay_trace(payload)
    assert replay_trace(b"") == ()


def test_source_data_remains_unchanged_by_replay() -> None:
    body = record()
    before = json.dumps(body)
    replay_trace(encoded(body))
    assert json.dumps(body) == before


def test_collector_action_redacts_approval_without_mutating_input(tmp_path: Path) -> None:
    from test_schemas import payloads

    from agentforge.core.schemas import ActionRequest, PolicyDecision

    action = ActionRequest.model_validate_json(
        json.dumps(dict(payloads()["ActionRequest"], approval_token="synthetic-approval"))
    )
    decision = PolicyDecision.model_validate_json(json.dumps(payloads()["PolicyDecision"]))
    collector = TraceCollector(tmp_path, "run-1", Redactor())
    try:
        proposed = collector.proposed_action(action)
        observed = collector.policy_decision(action, decision, parent_id=proposed.event.event_id)
        assert proposed.event.action is not None
        assert proposed.event.action.approval_token == "REDACTED"
        assert action.approval_token == "synthetic-approval"
        assert observed.event.actor == "gateway"
        assert b"synthetic-approval" not in (tmp_path / "trace.jsonl").read_bytes()
        assert len(collector.records) == 2
    finally:
        collector.close()


def test_bad_parent_or_modified_provenance_never_appended(tmp_path: Path) -> None:
    collector = TraceCollector(tmp_path, "run-1", Redactor(("agent",)))
    try:
        with pytest.raises(TraceError):
            collector.agent_claim("safe")
        assert (tmp_path / "trace.jsonl").read_bytes() == b""
    finally:
        collector.close()
    (tmp_path / "trace.jsonl").unlink()
    collector = TraceCollector(tmp_path, "run-1", Redactor())
    try:
        with pytest.raises(TraceError):
            collector.agent_claim("claim", parent_id="missing")
        assert (tmp_path / "trace.jsonl").read_bytes() == b""
        collector.agent_claim("claim")
        with (tmp_path / "trace.jsonl").open("ab") as stream:
            stream.write(b"partial")
        with pytest.raises(TraceError):
            _ = collector.records
    finally:
        collector.close()
