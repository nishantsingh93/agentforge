"""Read-only fixture snapshots. No fixture code is imported or executed."""

import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from agentforge.core.schemas import relative_path

MAX_FILE_BYTES = 1_048_576
MAX_SNAPSHOT_BYTES = 8_388_608
MAX_FILES = 256
MAX_DEPTH = 16


class FixtureError(ValueError):
    """A fixture is unsafe, unavailable, oversized, or inconsistent."""


@contextmanager
def open_directory(root: Path, relative: str) -> Iterator[int]:
    """Open a directory chain without following any relative symlink."""
    relative_path(relative)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.split("/"):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_file(directory: int, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_nlink != 1:
            raise FixtureError("expected a bounded regular file")
        chunks = bytearray()
        while len(chunks) <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(descriptor)
        if len(chunks) > limit:
            raise FixtureError("file exceeds size limit")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise FixtureError("file changed while reading")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def read_project_file(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> bytes:
    """Read a canonical project-relative file without traversing symlinks."""
    relative_path(relative)
    parts = relative.split("/")
    try:
        if len(parts) == 1:
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                return _read_file(descriptor, parts[0], limit)
            finally:
                os.close(descriptor)
        with open_directory(root, "/".join(parts[:-1])) as descriptor:
            return _read_file(descriptor, parts[-1], limit)
    except OSError as error:
        raise FixtureError(f"cannot safely read {relative}") from error


@dataclass(frozen=True)
class FixtureFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class FixtureSnapshot:
    digest: str
    files: tuple[FixtureFile, ...]


def snapshot_fixture(root: Path, directory: str) -> FixtureSnapshot:
    """Capture and hash a bounded tree; reject links and special files."""
    relative_path(directory)
    if not directory.startswith("fixtures/"):
        raise FixtureError("fixture directory must be under fixtures/")
    files: list[FixtureFile] = []
    total = 0
    nodes = 0

    def visit(descriptor: int, prefix: str, depth: int) -> None:
        nonlocal total, nodes
        if depth > MAX_DEPTH:
            raise FixtureError("fixture exceeds depth limit")
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_FILES:
                    raise FixtureError("fixture directory has too many entries")
        for name in sorted(names):
            nodes += 1
            if nodes > 1024:
                raise FixtureError("fixture exceeds entry limit")
            path = f"{prefix}{name}"
            relative_path(path)
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                try:
                    visit(child, path + "/", depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                content = _read_file(descriptor, name, MAX_FILE_BYTES)
                total += len(content)
                files.append(FixtureFile(path, content))
                if total > MAX_SNAPSHOT_BYTES or len(files) > MAX_FILES:
                    raise FixtureError("fixture exceeds snapshot limits")
            else:
                raise FixtureError("symlinks and special files are forbidden in fixtures")

    try:
        with open_directory(root, directory) as descriptor:
            visit(descriptor, "", 0)
    except OSError as error:
        raise FixtureError("cannot safely snapshot fixture") from error
    if not files:
        raise FixtureError("fixture must contain files")
    ordered = tuple(sorted(files, key=lambda entry: entry.path))
    manifest = [(entry.path, hashlib.sha256(entry.content).hexdigest()) for entry in ordered]
    encoded = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return FixtureSnapshot(digest, ordered)
