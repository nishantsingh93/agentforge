"""Sanitized evidence publication for trusted runner wiring and owned fixtures."""

import os
import re
import uuid
from pathlib import Path

from pydantic import JsonValue

from agentforge.core.artifacts import MAX_ARTIFACT_BYTES, ArtifactStore, digest_bytes
from agentforge.core.redaction import Redactor
from agentforge.core.schemas import EvidenceBundle, ToolResult
from agentforge.core.trace import TraceCollector, canonical_json


class EvidenceError(ValueError):
    """Evidence cannot be published as a complete validated bundle."""


class EvidenceCollector:
    """Owns a fresh run. Finalization seals both evidence and trace writes.

    Bundle revision hashes the canonical bundle payload excluding its revision.
    File and snapshot revisions hash their sanitized artifact bytes. The final
    bundle is also stored as a content-addressed object and as evidence.json.
    """

    def __init__(self, runs_root: Path, run_id: str, redactor: Redactor | None = None) -> None:
        self._redactor = redactor if redactor is not None else Redactor()
        if self._redactor.sanitize(run_id).value != run_id or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id
        ):
            raise EvidenceError("invalid or sensitive run identifier")
        self._store = ArtifactStore(runs_root, run_id)
        self._directory = os.open(runs_root / run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.trace = TraceCollector(runs_root / run_id, run_id, self._redactor)
        except Exception:
            os.close(self._directory)
            self._store.close()
            raise
        self._sealed = False

    def close(self) -> None:
        self.trace.close()
        self._store.close()
        if self._directory >= 0:
            os.close(self._directory)
            self._directory = -1

    def finalize(
        self,
        *,
        files: dict[str, str],
        diff: str,
        snapshots: dict[str, dict[str, JsonValue]],
    ) -> EvidenceBundle:
        if self._sealed or self._directory < 0:
            raise EvidenceError("evidence collector sealed or closed")
        # All supplied text, including names, is sanitized before hashing or writing.
        raw: dict[str, JsonValue] = {
            "files": dict(files),
            "diff": diff,
            "snapshots": {key: dict(value) for key, value in snapshots.items()},
        }
        sanitized = self._redactor.sanitize(raw)
        artifacts: list[bytes] = []
        try:
            safe = sanitized.value
            assert isinstance(safe, dict)
            safe_files, safe_snapshots = safe["files"], safe["snapshots"]
            assert isinstance(safe_files, dict) and isinstance(safe_snapshots, dict)
            refs = []
            states = []
            for path, content in safe_files.items():
                assert isinstance(content, str)
                data = content.encode()
                artifacts.append(data)
                refs.append(
                    dict(
                        kind="file",
                        path=path,
                        revision=digest_bytes(data),
                        start_line=1,
                        end_line=max(1, len(content.splitlines())),
                    )
                )
            for name, state in safe_snapshots.items():
                data = canonical_json(state)
                artifacts.append(data)
                states.append(dict(snapshot_id=name, revision=digest_bytes(data), state=state))
            records = self.trace.records
            rules = sorted(
                set(sanitized.rules).union(
                    rule for record in records for rule in record.redaction_rules
                )
            )
            commands: list[ToolResult] = [
                record.event.tool_result
                for record in records
                if record.event.tool_result is not None
            ]
            body = dict(
                schema_version="1",
                run_id=self._store.run_id,
                inspected_files=refs,
                diff=safe["diff"],
                commands=[c.model_dump(mode="json") for c in commands],
                snapshots=states,
                events=[
                    dict(kind="event", event_id=r.event.event_id, revision=r.revision)
                    for r in records
                ],
                redacted=bool(rules),
                redaction_notes=rules,
            )
            bundle = EvidenceBundle.model_validate_json(
                canonical_json(dict(body, revision=digest_bytes(canonical_json(body))))
            )
            published = canonical_json(bundle.model_dump(mode="json"))
            artifacts.append(published)
            if any(len(data) > MAX_ARTIFACT_BYTES for data in artifacts):
                raise EvidenceError("evidence exceeds artifact limits")
        except (ValueError, TypeError, AssertionError, RecursionError):
            raise EvidenceError("sanitized evidence contract invalid") from None
        # No writes above this point. Failure below seals the run rather than retrying
        # potentially inconsistent evidence. Unreferenced sanitized objects may remain.
        self._sealed = True
        self.trace.close()
        temporary = ".bundle-" + uuid.uuid4().hex
        try:
            for data in artifacts:
                self._store.put(data)
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=self._directory,
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(published)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(
                    temporary,
                    "evidence.json",
                    src_dir_fd=self._directory,
                    dst_dir_fd=self._directory,
                )
                os.fsync(self._directory)
            finally:
                os.unlink(temporary, dir_fd=self._directory)
        except OSError:
            raise EvidenceError("evidence publication failed") from None
        return bundle
