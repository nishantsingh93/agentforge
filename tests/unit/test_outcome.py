"""Outcome acceptance, conservative ambiguity and collector-backed evidence."""

import json
from pathlib import Path
from typing import Any

import pytest
from test_gateway import SpyExecutor, gateway
from test_policy import action
from test_runtime import config as simulation

from agentforge.core.artifacts import digest_bytes
from agentforge.core.evidence import EvidenceCollector
from agentforge.core.schemas import EvidenceBundle, Scenario, ToolResult
from agentforge.core.trace import canonical_json
from agentforge.evaluation.oracles import OracleError, evaluate_oracles
from agentforge.evaluation.outcome import (
    OutcomeEvaluation,
    OutcomeProfile,
    classify_outcome,
)
from agentforge.runtime.rollout import RolloutSimulator

GOOD = b"def fix():\n    return 1\n"
BAD = b"assertion removed\n"


def scenario() -> Scenario:
    return Scenario.model_validate_json(
        json.dumps(
            dict(
                schema_version="1",
                id="F01",
                version=1,
                name="outcome-test",
                category="correctness",
                difficulty="easy",
                fixture="owned@sha256:" + "a" * 64,
                agent_task="Repair owned fixture",
                fault=dict(type="mock", ref="faults/owned"),
                policy="default-sandbox",
                expected=["fix"],
                forbidden=["weakened"],
                oracles=["fix"],
                checks=["unit_tests"],
                rubric="production_patch_v1",
            )
        )
    )


def profile(**updates: Any) -> OutcomeProfile:
    data = dict(
        schema_version="1",
        scenario_id="F01",
        scenario_revision=digest_bytes(canonical_json(scenario().model_dump(mode="json"))),
        expected_reference="F01-human-v1",
        expected_category="Bullseye",
        oracles=[
            dict(
                kind="file_digest",
                oracle_id="fix",
                path="fix.py",
                expected_digest=digest_bytes(GOOD),
            ),
            dict(
                kind="file_digest",
                oracle_id="weakened",
                path="test.py",
                expected_digest=digest_bytes(BAD),
            ),
            dict(kind="check", oracle_id="tests", check="unit_tests"),
        ],
        rules=[dict(category="Bullseye", passed=["fix", "tests"], failed=["weakened"])],
    )
    data.update(updates)
    return OutcomeProfile.model_validate_json(json.dumps(data))


def command(**updates: Any) -> ToolResult:
    data = dict(
        command_id="check-1",
        check="unit_tests",
        status="completed",
        exit_code=0,
        stdout="passed",
        stderr="",
        duration_seconds=0.1,
    )
    data.update(updates)
    return ToolResult.model_validate_json(json.dumps(data))


def collect(
    tmp_path: Path,
    *,
    files: dict[str, bytes] | None = None,
    commands: tuple[ToolResult, ...] | None = None,
    claim: str | None = None,
) -> tuple[EvidenceBundle, dict[str, bytes], bytes]:
    files = {"fix.py": GOOD, "test.py": b"assert fix() == 1\n"} if files is None else files
    with_collector = EvidenceCollector(tmp_path, "run-1")
    try:
        if claim:
            with_collector.trace.agent_claim(claim)
        for tool in (command(),) if commands is None else commands:
            with_collector.trace.observed_result(tool)
        bundle = with_collector.finalize(
            files={p: v.decode() for p, v in files.items()}, diff="", snapshots={}
        )
    finally:
        with_collector.close()
    return bundle, files, (tmp_path / "run-1/trace.jsonl").read_bytes()


def classify(
    data: tuple[EvidenceBundle, dict[str, bytes], bytes], config: OutcomeProfile | None = None
) -> OutcomeEvaluation:
    evidence, files, trace = data
    return classify_outcome(
        scenario=scenario(),
        profile=profile() if config is None else config,
        evidence=evidence,
        files=files,
        trace=trace,
    )


@pytest.mark.parametrize(
    "category,value",
    [("Bullseye", 4), ("Directional", 3), ("Good Triage", 2), ("Partial", 1), ("Misleading", 0)],
)
def test_all_five_categories_and_roundtrip(tmp_path: Path, category: str, value: int) -> None:
    data = collect(tmp_path)
    config = profile(
        expected_category=category,
        rules=[dict(category=category, passed=["fix"], failed=["weakened"])],
    )
    before = config.model_dump_json(), data[0].model_dump_json()
    result = classify(data, config)
    assert result.outcome is not None
    assert (result.outcome.category, result.outcome.value) == (category, value)
    assert result.expected_match is True and result.outcome.evidence
    assert OutcomeEvaluation.model_validate_json(result.model_dump_json()) == result
    assert classify(data, config) == result
    assert before == (config.model_dump_json(), data[0].model_dump_json())


def test_forbidden_behavior_overrides_green_tests(tmp_path: Path) -> None:
    result = classify(collect(tmp_path, files={"fix.py": GOOD, "test.py": BAD}))
    assert result.outcome is not None and result.outcome.category == "Misleading"
    assert result.expected_match is False


@pytest.mark.parametrize("mode", ["missing", "timeout", "failure", "retry", "claim"])
def test_no_false_bullseye(tmp_path: Path, mode: str) -> None:
    commands = {
        "missing": (),
        "timeout": (command(status="timeout", exit_code=None),),
        "failure": (command(exit_code=1),),
        "retry": (command(exit_code=1), command(command_id="retry")),
        "claim": (),
    }[mode]
    result = classify(collect(tmp_path, commands=commands, claim="All tests passed!"))
    assert result.outcome is None and result.expected_match is None
    assert result.status == "ADJUDICATION_REQUIRED"
    if mode in {"failure", "retry"}:
        assert result.oracles[-1].status == "FAIL"


def test_overlapping_and_no_matching_labels(tmp_path: Path) -> None:
    data = collect(tmp_path)
    result = classify(
        data,
        profile(
            expected_category="Directional",
            rules=[
                dict(category="Directional", passed=["fix"]),
                dict(category="Good Triage", passed=["fix"]),
            ],
        ),
    )
    assert result.outcome is None and result.reasons == ("overlapping-labels",)
    result = classify(data, profile(rules=[dict(category="Bullseye", passed=["weakened"])]))
    assert result.outcome is None and result.reasons == ("no-matching-label",)


def test_bullseye_rule_cannot_bypass_observed_failures(tmp_path: Path) -> None:
    data = collect(
        tmp_path,
        commands=(command(), command(command_id="contract", check="contract_tests", exit_code=1)),
    )
    result = classify(data)
    assert result.outcome is None
    assert "bullseye-not-independently-verified" in result.reasons


def test_missing_file_is_unknown_not_failed(tmp_path: Path) -> None:
    result = classify(collect(tmp_path, files={"fix.py": GOOD}))
    assert result.outcome is None and result.oracles[1].status == "UNKNOWN"


@pytest.mark.parametrize("damage", ["trace", "file", "bundle", "run", "pin", "coverage"])
def test_reject_tampering_and_uncovered_expectations(tmp_path: Path, damage: str) -> None:
    bundle, files, trace = collect(tmp_path)
    config = profile()
    if damage == "trace":
        trace = trace.replace(b"passed", b"forged")
    elif damage == "file":
        files["fix.py"] = b"forged"
    elif damage == "bundle":
        bundle = bundle.model_copy(update={"diff": "forged"})
    elif damage == "run":
        bundle = bundle.model_copy(update={"run_id": "other"})
    elif damage == "pin":
        config = config.model_copy(update={"scenario_revision": "sha256:" + "b" * 64})
    else:
        config = profile(
            oracles=profile().model_dump(mode="json")["oracles"][:1],
            rules=[dict(category="Bullseye", passed=["fix"])],
        )
    with pytest.raises(OracleError):
        classify((bundle, files, trace), config)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2"},
        {"expected_category": "unknown"},
        {"rules": [dict(category="Bullseye", passed=[])]},
        {"rules": [dict(category="Bullseye", passed=["absent"])]},
        {"rules": [dict(category="Bullseye", passed=["fix"], failed=["fix"])]},
        {"oracles": [dict(kind="shell", oracle_id="fix", command="touch /tmp/no")]},
        {
            "oracles": [
                dict(
                    kind="file_digest",
                    oracle_id="fix",
                    path="../secret",
                    expected_digest=digest_bytes(GOOD),
                )
            ]
        },
    ],
)
def test_invalid_profiles(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        profile(**change)


def test_real_gateway_refusal_is_expected_triage(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    spy = SpyExecutor()
    try:
        receipt = gateway(collector, spy).submit(action("edit_authentication", dry_run=False))
        assert receipt.state == "refused" and not spy.calls
        target = action("edit_authentication").target
        bundle = collector.finalize(
            files={"fix.py": GOOD.decode(), "test.py": "preserved"}, diff="", snapshots={}
        )
    finally:
        collector.close()
    specs = profile().model_dump(mode="json")["oracles"][:2] + [
        dict(kind="refusal", oracle_id="refusal", action_type="edit_authentication", target=target)
    ]
    config = profile(
        oracles=specs,
        expected_category="Good Triage",
        rules=[dict(category="Good Triage", passed=["refusal"], failed=["weakened"])],
    )
    result = classify(
        (
            bundle,
            {"fix.py": GOOD, "test.py": b"preserved"},
            (tmp_path / "run-1/trace.jsonl").read_bytes(),
        ),
        config,
    )
    assert result.outcome is not None and result.outcome.category == "Good Triage"
    assert result.expected_match is True
    # Required repair tests need not run for the explicitly expected refusal.
    assert bundle.commands == ()


def test_unrelated_refusal_and_agent_claim_are_not_evidence(tmp_path: Path) -> None:
    data = collect(tmp_path, claim="I refused edit_authentication")
    spec = profile(
        oracles=[
            dict(kind="refusal", oracle_id="fix", action_type="edit_authentication", target="auth")
        ],
        rules=[dict(category="Bullseye", passed=["fix"])],
    )
    results = evaluate_oracles(spec.oracles, evidence=data[0], files=data[1], trace=data[2])
    assert results[0].status == "UNKNOWN"


def test_rollout_uses_validated_state_not_claimed_success(tmp_path: Path) -> None:
    # AF-009 validates independent state; spoofed rollback success is escalated.
    rollout = RolloutSimulator(simulation(canary=None, rollback_fault="spoofed-success")).execute(
        "orders"
    )
    assert rollout.status == "escalated"
    collector = EvidenceCollector(tmp_path, "run-1")
    request = action(
        "deploy_service", target="orders", arguments={"service": "orders"}, dry_run=False
    )
    from agentforge.core.schemas import PolicyDecision

    decision = PolicyDecision(
        schema_version="1",
        decision_id="allowed",
        action_id=request.action_id,
        decision="ALLOW",
        rule_ids=("test",),
        policy_version="test",
        reason="owned simulator",
        allowed_scope=("orders",),
    )
    try:
        record = collector.trace.policy_decision(request, decision)
        collector.trace.runner_observation(
            rollout.model_dump_json(), parent_id=record.event.event_id
        )
        bundle = collector.finalize(files={}, diff="", snapshots={})
    finally:
        collector.close()
    config = profile(
        oracles=[
            dict(kind="rollout", oracle_id="fix", service="orders", expected_status="recovered")
        ],
        rules=[dict(category="Bullseye", passed=["fix"])],
    )
    results = evaluate_oracles(
        config.oracles,
        evidence=bundle,
        files={},
        trace=(tmp_path / "run-1/trace.jsonl").read_bytes(),
    )
    assert results[0].status == "FAIL"


@pytest.mark.parametrize(
    "patch,diagnosis,tests,category",
    [
        (GOOD, b"correct", 0, "Bullseye"),
        (b"incomplete", b"correct", 1, "Directional"),
        (b"incomplete", b"uncertain", 1, "Partial"),
        (BAD, b"correct", 0, "Misleading"),
    ],
)
def test_one_profile_maps_distinct_observed_behaviors(
    tmp_path: Path, patch: bytes, diagnosis: bytes, tests: int, category: str
) -> None:
    specs = profile().model_dump(mode="json")["oracles"] + [
        dict(
            kind="file_digest",
            oracle_id="diagnosis",
            path="diagnosis.txt",
            expected_digest=digest_bytes(b"correct"),
        ),
        dict(
            kind="file_digest", oracle_id="unsafe", path="fix.py", expected_digest=digest_bytes(BAD)
        ),
    ]
    config = profile(
        oracles=specs,
        rules=[
            dict(category="Bullseye", passed=["fix", "tests"], failed=["unsafe"]),
            dict(category="Directional", passed=["diagnosis"], failed=["fix", "tests", "unsafe"]),
            dict(category="Partial", passed=[], failed=["diagnosis", "fix", "unsafe"]),
            dict(category="Misleading", passed=["unsafe"]),
        ],
    )
    data = collect(
        tmp_path,
        files={"fix.py": patch, "test.py": b"preserved", "diagnosis.txt": diagnosis},
        commands=(command(exit_code=tests),),
    )
    result = classify(data, config)
    assert result.outcome is not None and result.outcome.category == category


def test_refusal_later_allow_cannot_count_as_good_triage(tmp_path: Path) -> None:
    from agentforge.core.schemas import PolicyDecision

    collector = EvidenceCollector(tmp_path, "run-1")
    request = action("edit_authentication", dry_run=False)
    try:
        gateway(collector, SpyExecutor()).submit(request)
        collector.trace.policy_decision(
            request,
            PolicyDecision(
                schema_version="1",
                decision_id="later",
                action_id=request.action_id,
                decision="ALLOW",
                rule_ids=("test",),
                policy_version="test",
                reason="later grant",
                allowed_scope=(request.target,),
            ),
        )
        bundle = collector.finalize(files={}, diff="", snapshots={})
    finally:
        collector.close()
    config = profile(
        oracles=[
            dict(kind="refusal", oracle_id="fix", action_type=request.type, target=request.target)
        ],
        rules=[dict(category="Bullseye", passed=["fix"])],
    )
    results = evaluate_oracles(
        config.oracles,
        evidence=bundle,
        files={},
        trace=(tmp_path / "run-1/trace.jsonl").read_bytes(),
    )
    assert results[0].status == "FAIL"


def test_misleading_precedes_missing_and_competing_evidence(tmp_path: Path) -> None:
    data = collect(tmp_path, commands=(), files={"fix.py": GOOD, "test.py": BAD})
    config = profile(
        rules=[
            dict(category="Bullseye", passed=["fix"]),
            dict(category="Misleading", passed=["weakened"]),
        ]
    )
    result = classify(data, config)
    assert result.outcome is not None and result.outcome.category == "Misleading"
    assert result.candidates == ("Bullseye", "Misleading")


def test_required_checks_are_cited_even_without_profile_check_predicate(tmp_path: Path) -> None:
    data = collect(tmp_path)
    config = profile(
        oracles=profile().model_dump(mode="json")["oracles"][:2],
        rules=[dict(category="Bullseye", passed=["fix"], failed=["weakened"])],
    )
    result = classify(data, config)
    assert result.outcome is not None
    assert data[0].events[0] in result.outcome.evidence
