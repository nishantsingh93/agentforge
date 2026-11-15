"""Exercise all wire contracts with real JSON and adversarial payloads."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from agentforge.core.schemas import DIMENSIONS, MODELS, JudgeResult, export_json_schemas

DIGEST = "sha256:" + "a" * 64
EVENT = {"kind": "event", "event_id": "event-1", "revision": DIGEST}
FILE = {"kind": "file", "path": "src/orders.py", "revision": DIGEST, "start_line": 1, "end_line": 2}


def payloads() -> dict[str, dict[str, Any]]:
    action = {
        "schema_version": "1",
        "action_id": "action-1",
        "type": "read_file",
        "arguments": {"path": "src/orders.py"},
        "target": "src/orders.py",
        "environment": "sandbox",
        "requested_capabilities": ["read"],
        "blast_radius": "single_file",
        "reversibility": "reversible",
        "impact": dict.fromkeys(["availability", "data", "revenue", "security"], "none"),
        "preconditions": [],
        "approval_token": None,
        "idempotency_key": "request-1",
        "dry_run": True,
    }
    policy = {
        "schema_version": "1",
        "decision_id": "decision-1",
        "action_id": "action-1",
        "decision": "ALLOW",
        "rule_ids": ["allow-read"],
        "policy_version": "policy-v1",
        "reason": "Scoped fixture read",
        "allowed_scope": ["src/orders.py"],
    }
    judge = {
        "schema_version": "1",
        "run_id": "run-1",
        "dimension": "repository_awareness",
        "score": None,
        "status": "UNKNOWN",
        "findings": [],
        "evidence": [],
        "missing_evidence": ["Semantic judge unavailable offline"],
        "confidence": None,
        "judge_model": "offline",
        "prompt_version": "repository-v1",
    }
    outcome = {
        "schema_version": "1",
        "run_id": "run-1",
        "category": "Good Triage",
        "value": 2,
        "expected_reference": "refusal",
        "evidence": [EVENT],
        "confidence": 1.0,
    }
    return {
        "Scenario": {
            "schema_version": "1",
            "id": "F01",
            "version": 1,
            "name": "null-handling",
            "category": "correctness",
            "difficulty": "easy",
            "fixture": "orders@" + DIGEST,
            "agent_task": "Fix null handling",
            "fault": {"type": "fixture_patch", "ref": "faults/F01.patch"},
            "policy": "default-sandbox",
            "expected": ["null_rejected"],
            "forbidden": [],
            "oracles": ["null_rejected"],
            "checks": ["unit_tests"],
            "rubric": "production_patch_v1",
        },
        "ActionRequest": action,
        "PolicyDecision": policy,
        "TraceEvent": {
            "schema_version": "1",
            "event_id": "event-1",
            "run_id": "run-1",
            "sequence": 1,
            "timestamp": "2026-11-06T12:00:00Z",
            "actor": "gateway",
            "parent_id": None,
            "action": action,
            "policy_decision": policy,
            "tool_result": None,
            "evidence": [],
            "claim": None,
        },
        "EvidenceBundle": {
            "schema_version": "1",
            "run_id": "run-1",
            "revision": DIGEST,
            "inspected_files": [FILE],
            "diff": "",
            "commands": [],
            "snapshots": [],
            "events": [EVENT],
            "redacted": False,
            "redaction_notes": [],
        },
        "JudgeResult": judge,
        "OutcomeResult": outcome,
        "RunReport": {
            "schema_version": "1",
            "run_id": "run-1",
            "scenario_id": "F01",
            "quality_status": "INCOMPLETE",
            "weighted_quality": None,
            "judges": [dict(judge, dimension=dimension) for dimension in DIMENSIONS],
            "safety": "PASS",
            "outcome": outcome,
            "release_decision": "UNKNOWN",
            "metrics": {"blocked_attempts": {"numerator": 0, "denominator": 0}},
            "config": {"offline": True},
            "audit_artifacts": [EVENT],
        },
    }


@pytest.mark.parametrize("model", MODELS)
def test_json_roundtrip(model: Any) -> None:
    parsed = model.model_validate_json(json.dumps(payloads()[model.__name__]))
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("version", ["2", 1, True, None])
def test_unsupported_schema_version(model: Any, version: Any) -> None:
    payload = payloads()[model.__name__]
    payload["schema_version"] = version
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("model", MODELS)
def test_no_ignored_or_missing_fields(model: Any) -> None:
    payload = payloads()[model.__name__]
    payload["ignore_policy"] = True
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
    del payload["ignore_policy"]
    del payload["schema_version"]
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("name", "key", "value"),
    [
        ("ActionRequest", "type", "shell"),
        ("ActionRequest", "arguments", {"command": "touch /tmp/unsafe"}),
        ("ActionRequest", "arguments", {"path": "../secret"}),
        ("ActionRequest", "arguments", {"path": "/etc/passwd"}),
        ("ActionRequest", "arguments", {"path": "a\\..\\secret"}),
        ("ActionRequest", "arguments", {"path": "a//b"}),
        ("ActionRequest", "arguments", {"path": "a/./b"}),
        ("ActionRequest", "arguments", {"path": "C:/secret"}),
        ("ActionRequest", "arguments", {"path": "a\x00b"}),
        ("ActionRequest", "arguments", {"path": "src/orders.py", "content": "unexpected"}),
        ("ActionRequest", "environment", "production"),
        ("ActionRequest", "impact", {"availability": "none"}),
        ("ActionRequest", "dry_run", "false"),
        ("PolicyDecision", "decision", "BLOCK"),
        ("Scenario", "fault", {"type": "shell", "ref": "run.sh"}),
        ("Scenario", "version", "1"),
        ("Scenario", "checks", ["arbitrary_shell"]),
        ("Scenario", "fixture", "orders@latest"),
        ("Scenario", "forbidden", ["null_rejected"]),
        ("Scenario", "checks", ["unit_tests", "unit_tests"]),
        ("TraceEvent", "sequence", True),
        ("TraceEvent", "parent_id", "event-1"),
        ("TraceEvent", "timestamp", "2026-99-99T99:99:99Z"),
        ("JudgeResult", "score", 100.0),
        ("JudgeResult", "confidence", 1.0),
        ("JudgeResult", "missing_evidence", []),
        ("JudgeResult", "status", "PASS"),
        ("OutcomeResult", "value", 4),
        ("OutcomeResult", "confidence", 1.1),
        ("OutcomeResult", "confidence", float("nan")),
        ("OutcomeResult", "evidence", []),
        ("RunReport", "release_decision", "PASS"),
        ("RunReport", "weighted_quality", 100.0),
        ("RunReport", "quality_status", "COMPLETE"),
        ("RunReport", "metrics", {"escapes": {"numerator": 2, "denominator": 1}}),
    ],
)
def test_reject_invalid_contract(name: str, key: str, value: Any) -> None:
    payload = payloads()[name]
    payload[key] = value
    model = next(model for model in MODELS if model.__name__ == name)
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))


def test_export_all_versioned_json_schemas() -> None:
    exported = export_json_schemas()
    assert set(exported) == set(payloads())
    for schema in exported.values():
        assert schema["properties"]["schema_version"]["const"] == "1"
        assert schema["additionalProperties"] is False
    assert json.loads(json.dumps(exported)) == exported


def test_known_judgment_requires_grounding() -> None:
    model = JudgeResult
    payload = dict(payloads()["JudgeResult"], score=90.0, status="PASS", confidence=0.9)
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
    payload["evidence"] = [FILE]
    payload["missing_evidence"] = []
    assert model.model_validate_json(json.dumps(payload)).score == 90.0


def test_report_rejects_duplicate_dimensions_and_cross_run_judges() -> None:
    model = next(model for model in MODELS if model.__name__ == "RunReport")
    payload = payloads()["RunReport"]
    payload["judges"][1]["dimension"] = payload["judges"][0]["dimension"]
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
    payload = payloads()["RunReport"]
    payload["judges"][0]["run_id"] = "different-run"
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
