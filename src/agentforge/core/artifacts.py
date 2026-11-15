"""Internal content-addressed storage. Callers must sanitize before persistence.

This primitive is not a public evidence collector and does not detect secrets.
"""

import hashlib
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Self

MAX_ARTIFACT_BYTES = 8_388_608


class ArtifactError(ValueError):
    """Invalid, missing or corrupted artifact."""


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class ArtifactStore:
    """Exclusive run directory; immutable objects published with atomic links."""

    def __init__(self, runs_root: Path, run_id: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id) is None:
            raise ArtifactError("invalid run identifier")
        self.run_id = run_id
        self._directory = -1
        root = os.open(runs_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir(run_id, mode=0o700, dir_fd=root)
            run = os.open(run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                os.mkdir("objects", mode=0o700, dir_fd=run)
                self._directory = os.open(
                    "objects", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run
                )
                os.fsync(run)
            finally:
                os.close(run)
            os.fsync(root)
        finally:
            os.close(root)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._directory >= 0:
            os.close(self._directory)
            self._directory = -1

    def _require_open(self) -> int:
        if self._directory < 0:
            raise ArtifactError("artifact store is closed")
        return self._directory

    def put(self, data: bytes) -> str:
        directory = self._require_open()
        if type(data) is not bytes or len(data) > MAX_ARTIFACT_BYTES:
            raise ArtifactError("expected bounded immutable bytes")
        digest = digest_bytes(data)
        name = digest.removeprefix("sha256:")
        temporary = ".tmp-" + uuid.uuid4().hex
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode=0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            except FileExistsError:
                if self.read(digest) != data:
                    raise ArtifactError("content-address collision") from None
            os.fsync(directory)
        finally:
            os.unlink(temporary, dir_fd=directory)
        return digest

    def read(self, digest: str) -> bytes:
        directory = self._require_open()
        if re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is None:
            raise ArtifactError("invalid content reference")
        name = digest.removeprefix("sha256:")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
                    raise ArtifactError("invalid artifact file")
                data = stream.read(MAX_ARTIFACT_BYTES + 1)
        except OSError as error:
            raise ArtifactError("artifact unavailable") from error
        if len(data) > MAX_ARTIFACT_BYTES or digest_bytes(data) != digest:
            raise ArtifactError("artifact content does not match reference")
        return data
