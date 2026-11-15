"""Internal disposable snapshot executor; callers must pass through Gateway."""

import hashlib
import json
from typing import Protocol, Self

from pydantic import model_validator

from agentforge.core.fixtures import FixtureFile, FixtureSnapshot
from agentforge.core.schemas import ActionRequest, Contract, Digest, ToolResult
from agentforge.runtime.rollout import RolloutResult, RolloutSimulator
from agentforge.sandbox.runner import SandboxRunner, encode_snapshot


class Observation(Contract):
    # This is the raw in-memory fixture identity, not a persisted evidence revision.
    source_snapshot_digest: Digest
    content: str | None = None
    tool_result: ToolResult | None = None
    rollout: RolloutResult | None = None

    @model_validator(mode="after")
    def exclusive_observation(self) -> Self:
        if sum(value is not None for value in (self.content, self.tool_result, self.rollout)) > 1:
            raise ValueError("observation kinds cannot be mixed")
        return self


class Executor(Protocol):
    def execute(self, request: ActionRequest) -> Observation: ...


class FixtureExecutor:
    def __init__(
        self,
        snapshot: FixtureSnapshot,
        sandbox: SandboxRunner,
        *,
        simulator: RolloutSimulator | None = None,
    ) -> None:
        encode_snapshot(snapshot)
        self._snapshot = snapshot
        self._sandbox = sandbox
        self._simulator = simulator

    @property
    def snapshot(self) -> FixtureSnapshot:
        return self._snapshot

    def execute(self, request: ActionRequest) -> Observation:
        request = ActionRequest.model_validate_json(request.model_dump_json())
        if request.dry_run:
            raise ValueError("dry runs must not dispatch")
        if request.type == "deploy_service":
            if self._simulator is None or request.environment != "simulated-production":
                raise ValueError("disposable simulator required")
            assert request.arguments.service is not None
            result_rollout = self._simulator.execute(request.arguments.service)
            return Observation(source_snapshot_digest=self._snapshot.digest, rollout=result_rollout)
        if request.type == "run_check":
            assert request.arguments.check is not None
            result = self._sandbox.run(self._snapshot, request.arguments.check)
            return Observation(source_snapshot_digest=self._snapshot.digest, tool_result=result)
        if request.type not in {"read_file", "edit_file"}:
            raise ValueError("unsupported executor action")
        path = request.arguments.path
        entry = next((entry for entry in self._snapshot.files if entry.path == path), None)
        if entry is None:
            raise ValueError("only existing fixture files are supported")
        if request.type == "read_file":
            return Observation(
                source_snapshot_digest=self._snapshot.digest, content=entry.content.decode("utf-8")
            )
        content = request.arguments.content
        assert content is not None
        files = tuple(
            FixtureFile(file.path, content.encode()) if file.path == path else file
            for file in self._snapshot.files
        )
        manifest = [
            (file.path, hashlib.sha256(file.content).hexdigest())
            for file in sorted(files, key=lambda file: file.path)
        ]
        digest = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        candidate = FixtureSnapshot(digest, files)
        encode_snapshot(candidate)  # Validate bounds and structure before mutation.
        self._snapshot = candidate
        return Observation(source_snapshot_digest=candidate.digest)
