"""Sandbox contract/lifecycle tests; spies are not containment evidence."""

import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from agentforge.core.fixtures import FixtureFile, FixtureSnapshot
from agentforge.sandbox.runner import (
    OUTPUT_LIMIT,
    DockerTransport,
    ProcessResult,
    SandboxCleanupError,
    SandboxConfig,
    SandboxRunner,
    SandboxUnavailable,
    encode_snapshot,
)

IMAGE = "python@sha256:" + "a" * 64
CONFIG = SandboxConfig("unix:///tmp/owned-docker.sock", IMAGE)


def snapshot(files: tuple[FixtureFile, ...] | None = None) -> FixtureSnapshot:
    entries = files or (FixtureFile("test_owned.py", b"# never executed on host\n"),)
    manifest = [
        (file.path, hashlib.sha256(file.content).hexdigest())
        for file in sorted(entries, key=lambda f: f.path)
    ]
    digest = (
        "sha256:" + hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()
    )
    return FixtureSnapshot(digest, entries)


class FakeDocker:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes, float]] = []
        self.run_result = ProcessResult(0, b"observed stdout", b"observed stderr")
        self.info_result = ProcessResult(0, b"linux\n")
        self.image_result = ProcessResult(
            0,
            json.dumps(
                [{"Os": "linux", "RepoDigests": [IMAGE], "Config": {"Volumes": None}}]
            ).encode(),
        )
        self.list_result = ProcessResult(0)
        self.remove_result = ProcessResult(0)
        self.run_error: OSError | None = None

    def execute(self, argv: Sequence[str], data: bytes, timeout: float) -> ProcessResult:
        args = list(argv)
        self.calls.append((args, data, timeout))
        command = args[5]
        if command == "info":
            return self.info_result
        if command == "image":
            return self.image_result
        if command == "run":
            if self.run_error is not None:
                raise self.run_error
            return self.run_result
        if command == "rm":
            return self.remove_result
        if command == "ps":
            return self.list_result
        raise AssertionError(f"unexpected command {command}")


def runner(fake: FakeDocker) -> SandboxRunner:
    return SandboxRunner(CONFIG, transport=fake, find_docker=lambda _: "/owned/docker")


def test_missing_docker_has_no_execution() -> None:
    fake = FakeDocker()
    with pytest.raises(SandboxUnavailable, match="no host fallback"):
        SandboxRunner(CONFIG, transport=fake, find_docker=lambda _: None).run(snapshot())
    assert fake.calls == []


@pytest.mark.parametrize("which", ["info", "image"])
def test_failed_preflight_never_runs_fixture(which: str) -> None:
    fake = FakeDocker()
    if which == "info":
        fake.info_result = ProcessResult(1)
    else:
        fake.image_result = ProcessResult(1)
    with pytest.raises(SandboxUnavailable):
        runner(fake).run(snapshot())
    assert all(call[0][5] not in {"run", "rm"} for call in fake.calls)


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        {},
        [{"Os": "windows", "Config": {}, "RepoDigests": [IMAGE]}],
        [{"Os": "linux", "Config": {"Volumes": {"/data": {}}}, "RepoDigests": [IMAGE]}],
        [{"Os": "linux", "Config": {}, "RepoDigests": []}],
    ],
)
def test_image_metadata_rejected(metadata: object) -> None:
    fake = FakeDocker()
    fake.image_result = ProcessResult(0, json.dumps(metadata).encode())
    with pytest.raises(SandboxUnavailable):
        runner(fake).run(snapshot())
    assert all(call[0][5] != "run" for call in fake.calls)


@pytest.mark.parametrize(
    "host", ["tcp://prod:2375", "ssh://prod", "unix://relative", "unix:///tmp/../socket"]
)
def test_reject_remote_or_ambiguous_socket(host: str) -> None:
    with pytest.raises(ValueError):
        SandboxConfig(host, IMAGE)


@pytest.mark.parametrize(
    "image", ["python:latest", "--privileged", "python@sha256:abc", "p\n@sha256:" + "a" * 64]
)
def test_reject_unpinned_image(image: str) -> None:
    with pytest.raises(ValueError):
        SandboxConfig(CONFIG.docker_host, image)


@pytest.mark.parametrize("timeout", [0.0, 61.0, float("nan"), float("inf"), True])
def test_reject_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        SandboxConfig(CONFIG.docker_host, IMAGE, timeout)


def test_snapshot_validation_precedes_docker() -> None:
    fake = FakeDocker()
    invalid = [
        FixtureSnapshot("sha256:" + "b" * 64, snapshot().files),
        snapshot((FixtureFile("../escape", b"x"),)),
        snapshot((FixtureFile("/escape", b"x"),)),
        snapshot((FixtureFile("a", b"x"), FixtureFile("a", b"y"))),
        snapshot((FixtureFile("a", b"x"), FixtureFile("a/b", b"y"))),
        snapshot((FixtureFile("a", b"x" * 1_048_577),)),
        FixtureSnapshot("sha256:" + "a" * 64, ()),
    ]
    for item in invalid:
        with pytest.raises(ValueError):
            runner(fake).run(item)
    with pytest.raises(ValueError, match="unsupported"):
        runner(fake).run(snapshot(), "shell")
    assert fake.calls == []


def test_confined_argv_observed_output_and_cleanup() -> None:
    fake = FakeDocker()
    observed = runner(fake).run(snapshot())
    argv, data, timeout = next(call for call in fake.calls if call[0][5] == "run")
    assert json.loads(data)["digest"] == snapshot().digest
    for flag, value in {
        "--host": CONFIG.docker_host,
        "--pull": "never",
        "--network": "none",
        "--ipc": "none",
        "--log-driver": "none",
        "--user": "65532:65532",
        "--cap-drop": "ALL",
        "--security-opt": "no-new-privileges=true",
        "--memory": "256m",
        "--memory-swap": "256m",
        "--pids-limit": "64",
        "--cpus": "1",
        "--workdir": "/workspace",
        "--entrypoint": "/usr/local/bin/python",
    }.items():
        assert argv[argv.index(flag) + 1] == value
    assert "--read-only" in argv and "--no-healthcheck" in argv
    assert "--rm" in argv and "--privileged" not in argv
    assert not {"--volume", "-v", "--mount", "--pid", "--device", "--publish"} & set(argv)
    assert "noexec" in argv[argv.index("--tmpfs") + 1]
    assert argv.index("-i") < argv.index(IMAGE) < argv.index("-I")
    name = argv[argv.index("--name") + 1]
    assert fake.calls[-2][0][-3:] == ["rm", "--force", name]
    assert fake.calls[-1][0][5] == "ps"
    assert not Path(argv[4]).exists()
    assert observed.command_id == name
    assert observed.status == "completed" and observed.exit_code == 0
    assert observed.stdout == "observed stdout" and observed.stderr == "observed stderr"
    assert timeout == 30
    assert observed.duration_seconds >= 0


@pytest.mark.parametrize(
    ("process", "expected"),
    [
        (ProcessResult(-9, status="timeout"), "timeout"),
        (ProcessResult(-9, status="output_limit"), "error"),
        (ProcessResult(125), "error"),
        (ProcessResult(1, b"tests passed"), "completed"),
    ],
)
def test_timeout_limit_and_failure_are_not_success(process: ProcessResult, expected: str) -> None:
    fake = FakeDocker()
    fake.run_result = process
    result = runner(fake).run(snapshot())
    assert result.status == expected
    assert result.exit_code == process.exit_code
    assert fake.calls[-2][0][5] == "rm"


@pytest.mark.parametrize(
    "result",
    [
        ProcessResult(1),
        ProcessResult(0, b"agentforge-still-running"),
        ProcessResult(-9, status="timeout"),
    ],
)
def test_cleanup_failure_is_explicit(result: ProcessResult) -> None:
    fake = FakeDocker()
    fake.list_result = result
    with pytest.raises(SandboxCleanupError) as error:
        runner(fake).run(snapshot())
    assert error.value.container_name.startswith("agentforge-")


def test_transport_error_still_attempts_cleanup() -> None:
    fake = FakeDocker()
    fake.run_error = OSError("owned transport failure")
    with pytest.raises(OSError, match="owned transport failure"):
        runner(fake).run(snapshot())
    assert fake.calls[-2][0][5] == "rm"


def test_each_run_has_distinct_name() -> None:
    fake = FakeDocker()
    first = runner(fake).run(snapshot())
    second = runner(fake).run(snapshot())
    assert first.command_id != second.command_id


def test_encoding_is_json_not_executable_command() -> None:
    data = encode_snapshot(snapshot((FixtureFile("quoted'file.py", b"untrusted data"),)))
    assert json.loads(data)["files"][0]["path"] == "quoted'file.py"


def test_real_transport_bounds_output_and_time() -> None:
    # These are fixed trusted transport probes, not fixture code or a host fallback.
    transport = DockerTransport()
    noisy = transport.execute(
        [sys.executable, "-I", "-c", "import os; os.write(1,b'x'*2000000)"], b"", 3
    )
    assert noisy.status == "output_limit" and len(noisy.stdout) == OUTPUT_LIMIT
    slow = transport.execute([sys.executable, "-I", "-c", "import time; time.sleep(5)"], b"", 0.1)
    assert slow.status == "timeout"


def test_transport_drains_both_streams_and_does_not_inherit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTFORGE_SYNTHETIC_SECRET", "not-a-real-secret")
    script = (
        "import os,sys; data=sys.stdin.buffer.read(); os.write(1,data); "
        "os.write(2,str(os.getenv('AGENTFORGE_SYNTHETIC_SECRET')).encode())"
    )
    result = DockerTransport().execute([sys.executable, "-I", "-c", script], b"x" * 200000, 3)
    assert result.status == "completed" and result.exit_code == 0
    assert result.stdout == b"x" * 200000 and result.stderr == b"None"


def test_interrupted_creation_requires_acknowledged_removal() -> None:
    fake = FakeDocker()
    fake.run_result = ProcessResult(-9, status="timeout")
    fake.remove_result = ProcessResult(1)
    with pytest.raises(SandboxCleanupError):
        runner(fake).run(snapshot())


def test_auto_removed_completed_container_allows_independent_absence_check() -> None:
    fake = FakeDocker()
    fake.remove_result = ProcessResult(1)
    assert runner(fake).run(snapshot()).status == "completed"


@pytest.mark.parametrize("returned", ["sha256:" + "b" * 64, None, "python:latest"])
def test_local_image_id_mismatch_never_executes(returned: str | None) -> None:
    image_id = "sha256:" + "a" * 64
    fake = FakeDocker()
    fake.image_result = ProcessResult(
        0, json.dumps([{"Os": "linux", "Id": returned, "Config": {"Volumes": None}}]).encode()
    )
    sandbox = SandboxRunner(
        SandboxConfig(CONFIG.docker_host, image_id),
        transport=fake,
        find_docker=lambda _: "/owned/docker",
    )
    with pytest.raises(SandboxUnavailable):
        sandbox.run(snapshot())
    assert all(call[0][5] != "run" for call in fake.calls)


def test_exact_local_image_id_without_repository_digest() -> None:
    image_id = "sha256:" + "a" * 64
    fake = FakeDocker()
    fake.image_result = ProcessResult(
        0,
        json.dumps(
            [{"Os": "linux", "Id": image_id, "Config": {"Volumes": None}, "RepoDigests": []}]
        ).encode(),
    )
    sandbox = SandboxRunner(
        SandboxConfig(CONFIG.docker_host, image_id),
        transport=fake,
        find_docker=lambda _: "/owned/docker",
    )
    assert sandbox.run(snapshot()).exit_code == 0
    argv = next(call[0] for call in fake.calls if call[0][5] == "run")
    assert image_id in argv and argv[argv.index("--pull") + 1] == "never"


@pytest.mark.parametrize("image_id", ["sha256:abc", "sha256:" + "A" * 64, "local:latest"])
def test_invalid_local_image_id_rejected(image_id: str) -> None:
    with pytest.raises(ValueError):
        SandboxConfig(CONFIG.docker_host, image_id)
