"""Collector persistence, provenance, and atomic publication regressions."""

from pathlib import Path

import pytest

from agentforge.core.artifacts import digest_bytes
from agentforge.core.evidence import EvidenceCollector, EvidenceError
from agentforge.core.redaction import Redactor
from agentforge.core.schemas import ToolResult
from agentforge.core.trace import TraceError, canonical_json, replay_trace


def failed_result() -> ToolResult:
    return ToolResult(
        command_id="cmd-1",
        check="unit_tests",
        status="completed",
        exit_code=1,
        stdout="password=synthetic-pass\nfailed",
        stderr="Bearer synthetic-header",
        duration_seconds=0.1,
    )


def test_sanitized_bundle_provenance_and_revisions(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1", Redactor(("synthetic-literal",)))
    try:
        claim = collector.trace.agent_claim("All tests passed synthetic-literal")
        observed = collector.trace.observed_result(failed_result(), parent_id=claim.event.event_id)
        bundle = collector.finalize(
            files={"src/main.py": "password=synthetic-file\nprint('ok')\n"},
            diff="+api_key=synthetic-diff\n",
            snapshots={"before": {"access_token": "synthetic-token", "count": 1}},
        )
        assert bundle.commands[0].exit_code == 1
        assert bundle.redacted
        assert bundle.snapshots[0].state["access_token"] == "REDACTED"
        objects = tmp_path / "run-1/objects"
        file = bundle.inspected_files[0]
        assert (objects / file.revision[7:]).read_bytes() == b"REDACTED\nprint('ok')\n"
        assert file.end_line == 2
        assert bundle.snapshots[0].revision == digest_bytes(
            canonical_json(bundle.snapshots[0].state)
        )
        assert bundle.revision == digest_bytes(
            canonical_json(bundle.model_dump(mode="json", exclude={"revision"}))
        )
        replay = replay_trace((tmp_path / "run-1/trace.jsonl").read_bytes(), observed.revision)
        assert replay[0].event.actor == "agent" and replay[0].event.tool_result is None
        assert replay[1].event.actor == "executor"
        for path in (tmp_path / "run-1").rglob("*"):
            if path.is_file():
                assert b"synthetic-" not in path.read_bytes()
        with pytest.raises(EvidenceError, match="sealed"):
            collector.finalize(files={}, diff="", snapshots={})
        with pytest.raises(TraceError):
            collector.trace.agent_claim("late claim")
    finally:
        collector.close()


def test_invalid_contract_writes_nothing_and_hides_input(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1", Redactor(("unit_tests",)))
    try:
        with pytest.raises(TraceError) as error:
            collector.trace.observed_result(failed_result())
        assert "synthetic-pass" not in str(error.value)
        assert error.value.__suppress_context__
        assert (tmp_path / "run-1/trace.jsonl").read_bytes() == b""
        with pytest.raises(EvidenceError):
            collector.finalize(files={"../bad": "password=synthetic-pass"}, diff="", snapshots={})
        assert not list((tmp_path / "run-1/objects").iterdir())
    finally:
        collector.close()


def test_existing_final_bundle_never_overwritten(tmp_path: Path) -> None:
    collector = EvidenceCollector(tmp_path, "run-1")
    path = tmp_path / "run-1/evidence.json"
    path.write_bytes(b"original")
    try:
        with pytest.raises(EvidenceError, match="publication"):
            collector.finalize(files={}, diff="", snapshots={})
        assert path.read_bytes() == b"original"
        assert not list(path.parent.glob(".bundle-*"))
    finally:
        collector.close()


def test_interrupted_final_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    real_link = os.link

    def broken_link(src: str, dst: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
        if dst == "evidence.json":
            raise OSError("synthetic failure")
        real_link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    collector = EvidenceCollector(tmp_path, "run-1")
    try:
        monkeypatch.setattr("agentforge.core.evidence.os.link", broken_link)
        with pytest.raises(EvidenceError):
            collector.finalize(files={}, diff="", snapshots={})
        assert not (tmp_path / "run-1/evidence.json").exists()
        assert not list((tmp_path / "run-1").glob(".bundle-*"))
    finally:
        collector.close()


def test_partial_trace_write_prevents_continuation_and_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    real_write = os.write

    def partial(fd: int, data: bytes) -> int:
        return real_write(fd, data[:10])

    collector = EvidenceCollector(tmp_path, "run-1")
    try:
        monkeypatch.setattr("agentforge.core.trace.os.write", partial)
        with pytest.raises(TraceError, match="append failed"):
            collector.trace.agent_claim("claim")
        with pytest.raises(TraceError, match="failed"):
            collector.trace.agent_claim("another")
        with pytest.raises(EvidenceError):
            collector.finalize(files={}, diff="", snapshots={})
        assert not (tmp_path / "run-1/evidence.json").exists()
    finally:
        collector.close()


def test_changed_file_content_has_distinct_revision(tmp_path: Path) -> None:
    revisions = []
    for index, content in enumerate(("version one", "version two")):
        collector = EvidenceCollector(tmp_path, f"run-{index}")
        try:
            bundle = collector.finalize(files={"source.py": content}, diff="", snapshots={})
            revisions.append(bundle.inspected_files[0].revision)
            assert not bundle.redacted and not bundle.redaction_notes
        finally:
            collector.close()
    assert revisions[0] != revisions[1]


def test_sandbox_transport_to_collector_contract(tmp_path: Path) -> None:
    # This exercises the adapter boundary, not real Docker containment.
    from test_sandbox import FakeDocker, runner, snapshot

    from agentforge.sandbox.runner import ProcessResult

    transport = FakeDocker()
    transport.run_result = ProcessResult(1, b"password=synthetic-pipeline\nfailure", b"")
    result = runner(transport).run(snapshot())
    collector = EvidenceCollector(tmp_path, "run-1")
    try:
        collector.trace.observed_result(result)
        bundle = collector.finalize(files={}, diff="", snapshots={})
        assert bundle.commands[0].exit_code == 1
        assert bundle.commands[0].stdout == "REDACTED\nfailure"
        assert result.stdout == "password=synthetic-pipeline\nfailure"
    finally:
        collector.close()
