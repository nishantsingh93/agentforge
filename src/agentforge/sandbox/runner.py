"""Bounded local Docker executor for owned disposable fixtures only."""

import base64
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Literal, Protocol, cast

from agentforge.core.fixtures import (
    MAX_DEPTH,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_SNAPSHOT_BYTES,
    FixtureSnapshot,
)
from agentforge.core.schemas import CheckName, ToolResult, relative_path
from agentforge.sandbox.bootstrap import BOOTSTRAP

OUTPUT_LIMIT = 1_048_576
PAYLOAD_LIMIT = 12_000_000


class SandboxUnavailable(RuntimeError):
    """Execution cannot safely start; there is no host fallback."""


class SandboxCleanupError(RuntimeError):
    """Container absence could not be verified; retain its name for recovery."""

    def __init__(self, container_name: str) -> None:
        self.container_name = container_name
        super().__init__(f"cleanup unverified for {container_name}")


@dataclass(frozen=True)
class SandboxConfig:
    docker_host: str
    image: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"unix:///[A-Za-z0-9_./-]+", self.docker_host):
            raise ValueError("an explicit local Unix Docker socket is required")
        if any(part in {"", ".", ".."} for part in self.docker_host[8:].split("/")):
            raise ValueError("Docker socket path must be canonical")
        if not re.fullmatch(r"(?:[a-z0-9][a-z0-9./:_-]*@)?sha256:[a-f0-9]{64}", self.image):
            raise ValueError("a reviewed digest-pinned image is required")
        if isinstance(self.timeout_seconds, bool) or not 1 <= self.timeout_seconds <= 60:
            raise ValueError("timeout must be between 1 and 60 seconds")


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    status: Literal["completed", "timeout", "output_limit"] = "completed"


class Transport(Protocol):
    def execute(self, argv: Sequence[str], data: bytes, timeout: float) -> ProcessResult: ...


class DockerTransport:
    """Drain pipes concurrently with bounded memory, input, and wall time."""

    def execute(self, argv: Sequence[str], data: bytes, timeout: float) -> ProcessResult:
        if len(data) > PAYLOAD_LIMIT:
            raise ValueError("input limit exceeded")
        # Do not inherit credentials, contexts, home configuration, or proxy variables.
        environment = {"PATH": os.defpath, "LC_ALL": "C"}
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            shell=False,
            close_fds=True,
        )
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        output = {"stdout": bytearray(), "stderr": bytearray()}
        status: Literal["completed", "timeout", "output_limit"] = "completed"
        deadline = time.monotonic() + timeout
        offset = 0
        try:
            with selectors.DefaultSelector() as selector:
                for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                os.set_blocking(process.stdin.fileno(), False)
                if data:
                    selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                else:
                    process.stdin.close()
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        status = "timeout"
                        break
                    for key, _ in selector.select(min(remaining, 0.1)):
                        if key.data == "stdin":
                            try:
                                offset += os.write(key.fd, data[offset : offset + 65536])
                            except BlockingIOError:
                                continue
                            except BrokenPipeError:
                                offset = len(data)
                            if offset == len(data):
                                selector.unregister(key.fileobj)
                                process.stdin.close()
                        else:
                            try:
                                chunk = os.read(key.fd, 65536)
                            except BlockingIOError:
                                continue
                            if not chunk:
                                selector.unregister(key.fileobj)
                            else:
                                buffer = output[key.data]
                                space = OUTPUT_LIMIT - len(buffer)
                                buffer.extend(chunk[:space])
                                if len(chunk) > space:
                                    status = "output_limit"
                        if status != "completed":
                            break
                    if status != "completed":
                        break
            if status == "completed":
                try:
                    process.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    status = "timeout"
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        return ProcessResult(
            process.returncode, bytes(output["stdout"]), bytes(output["stderr"]), status
        )


def encode_snapshot(snapshot: FixtureSnapshot) -> bytes:
    """Revalidate even manually constructed dataclasses before any Docker call."""
    if not 1 <= len(snapshot.files) <= MAX_FILES:
        raise ValueError("invalid fixture file count")
    names: set[str] = set()
    total = 0
    manifest = []
    files = []
    for entry in sorted(snapshot.files, key=lambda item: item.path):
        relative_path(entry.path)
        if len(entry.path) > 4096 or len(entry.path.split("/")) > MAX_DEPTH + 1:
            raise ValueError("fixture path exceeds limits")
        if entry.path in names or type(entry.content) is not bytes:
            raise ValueError("duplicate file or mutable content")
        names.add(entry.path)
        total += len(entry.content)
        if len(entry.content) > MAX_FILE_BYTES or total > MAX_SNAPSHOT_BYTES:
            raise ValueError("fixture exceeds size limits")
        manifest.append((entry.path, hashlib.sha256(entry.content).hexdigest()))
        files.append(
            {"path": entry.path, "content": base64.b64encode(entry.content).decode("ascii")}
        )
    for name in names:
        parts = name.split("/")
        if any("/".join(parts[:index]) in names for index in range(1, len(parts))):
            raise ValueError("file/directory collision")
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    if digest != snapshot.digest:
        raise ValueError("fixture digest mismatch")
    data = json.dumps({"digest": digest, "files": files}, separators=(",", ":")).encode()
    if len(data) > PAYLOAD_LIMIT:
        raise ValueError("encoded fixture too large")
    return data


class SandboxRunner:
    def __init__(
        self,
        config: SandboxConfig,
        *,
        transport: Transport | None = None,
        find_docker: Callable[[str], str | None] = shutil.which,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.transport = transport if transport is not None else DockerTransport()
        self.find_docker = find_docker
        self.clock = clock

    def preflight(self) -> None:
        """Check the local daemon and pinned image without executing a fixture."""
        docker = self.find_docker("docker")
        if docker is None:
            raise SandboxUnavailable("Docker executable unavailable; no host fallback")
        with TemporaryDirectory(prefix="agentforge-docker-config-") as directory:
            self._preflight([docker, "--host", self.config.docker_host, "--config", directory])

    def _require(self, argv: list[str]) -> ProcessResult:
        try:
            result = self.transport.execute(argv, b"", 5.0)
        except OSError as error:
            raise SandboxUnavailable("local Docker unavailable") from error
        if result.status != "completed" or result.exit_code != 0:
            raise SandboxUnavailable("Docker preflight failed; no fixture execution")
        return result

    def _preflight(self, prefix: list[str]) -> None:
        daemon = self._require([*prefix, "info", "--format", "{{.OSType}}"])
        if daemon.stdout.strip() != b"linux":
            raise SandboxUnavailable("Linux container daemon required")
        inspected = self._require([*prefix, "image", "inspect", self.config.image])
        try:
            images = json.loads(inspected.stdout)
            if not isinstance(images, list) or len(images) != 1:
                raise ValueError("expected one image")
            image = images[0]
            if image["Os"] != "linux" or image["Config"].get("Volumes"):
                raise ValueError("image must be Linux without declared volumes")
            if self.config.image.startswith("sha256:"):
                if image.get("Id") != self.config.image:
                    raise ValueError("local image ID not confirmed")
            elif (
                not isinstance(image["RepoDigests"], list)
                or self.config.image not in image["RepoDigests"]
            ):
                raise ValueError("image digest not confirmed")
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise SandboxUnavailable("invalid or unsafe pinned image metadata") from error

    def _cleanup(self, prefix: list[str], name: str, interrupted: bool) -> None:
        try:
            removed = self.transport.execute([*prefix, "rm", "--force", name], b"", 5.0)
            # A successful list query establishes absence; a failed inspect cannot.
            result = self.transport.execute(
                [*prefix, "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
                b"",
                5.0,
            )
            if result.status != "completed" or result.exit_code != 0 or result.stdout.strip():
                raise SandboxCleanupError(name)
            # Interrupted creation may still be in flight at the daemon. An empty
            # list alone is insufficient unless removal was also acknowledged.
            if interrupted and (removed.status != "completed" or removed.exit_code != 0):
                raise SandboxCleanupError(name)
        except OSError as error:
            raise SandboxCleanupError(name) from error

    def run(self, snapshot: FixtureSnapshot, check: str = "unit_tests") -> ToolResult:
        if check not in {"unit_tests", "lint", "typecheck", "build"}:
            raise ValueError("unsupported sandbox check")
        data = encode_snapshot(snapshot)
        docker = self.find_docker("docker")
        if docker is None:
            raise SandboxUnavailable("Docker executable unavailable; no host fallback")
        name = "agentforge-" + uuid.uuid4().hex
        with TemporaryDirectory(prefix="agentforge-docker-config-") as directory:
            prefix = [docker, "--host", self.config.docker_host, "--config", directory]
            self._preflight(prefix)
            argv = [
                *prefix,
                "run",
                "--rm",
                "--pull",
                "never",
                "--name",
                name,
                "--label",
                "agentforge.disposable=true",
                "--log-driver",
                "none",
                "--network",
                "none",
                "--ipc",
                "none",
                "--read-only",
                "--user",
                "65532:65532",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges=true",
                "--pids-limit",
                "64",
                "--memory",
                "256m",
                "--memory-swap",
                "256m",
                "--cpus",
                "1",
                "--ulimit",
                "nofile=256:256",
                "--ulimit",
                "core=0:0",
                "--tmpfs",
                "/workspace:rw,nosuid,nodev,noexec,size=64m,uid=65532,gid=65532,mode=0700",
                "--workdir",
                "/workspace",
                "--no-healthcheck",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--env",
                "TMPDIR=/workspace/tmp",
                "--entrypoint",
                "/usr/local/bin/python",
                "-i",
                self.config.image,
                "-I",
                "-c",
                BOOTSTRAP,
                check,
            ]
            started = self.clock()
            interrupted = True
            try:
                observed = self.transport.execute(argv, data, self.config.timeout_seconds)
                interrupted = observed.status != "completed" or (
                    observed.exit_code is None or observed.exit_code < 0
                )
            finally:
                self._cleanup(prefix, name, interrupted)
            status: Literal["completed", "timeout", "error"] = "completed"
            if observed.status == "timeout":
                status = "timeout"
            elif observed.status == "output_limit" or observed.exit_code in {125, 126, 127}:
                status = "error"
            return ToolResult(
                command_id=name,
                check=cast(CheckName, check),
                status=status,
                exit_code=observed.exit_code,
                stdout=observed.stdout.decode("utf-8", errors="replace"),
                stderr=observed.stderr.decode("utf-8", errors="replace"),
                duration_seconds=max(0.0, self.clock() - started),
            )
