"""Fixture snapshots preserve bytes and reject filesystem escape mechanisms."""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentforge.core.fixtures import FixtureError, read_project_file, snapshot_fixture


def fixture_tree(tmp_path: Path) -> Path:
    directory = tmp_path / "fixtures" / "demo"
    directory.mkdir(parents=True)
    (directory / "app.py").write_bytes(b"def answer(): return 42\n")
    return directory


def test_stable_immutable_snapshot(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    first = snapshot_fixture(tmp_path, "fixtures/demo")
    assert snapshot_fixture(tmp_path, "fixtures/demo") == first
    assert first.files[0].path == "app.py"
    field = "content"
    with pytest.raises(FrozenInstanceError):
        setattr(first.files[0], field, b"changed")
    (directory / "app.py").write_bytes(b"changed")
    assert first.files[0].content == b"def answer(): return 42\n"
    assert snapshot_fixture(tmp_path, "fixtures/demo").digest != first.digest


def test_digest_covers_file_names(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    first = snapshot_fixture(tmp_path, "fixtures/demo")
    (directory / "app.py").rename(directory / "other.py")
    assert snapshot_fixture(tmp_path, "fixtures/demo").digest != first.digest


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "fixtures/../secret", "a\\b"])
def test_read_rejects_traversal(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        read_project_file(tmp_path, path)


def test_reject_file_symlink(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    secret = tmp_path / "secret"
    secret.write_bytes(b"private")
    (directory / "link").symlink_to(secret)
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/demo")
    with pytest.raises(FixtureError):
        read_project_file(tmp_path, "fixtures/demo/link")


def test_reject_directory_symlink(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    (tmp_path / "fixtures" / "alias").symlink_to(directory, target_is_directory=True)
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/alias")
    with pytest.raises(FixtureError):
        read_project_file(tmp_path, "fixtures/alias/app.py")


def test_reject_hardlink(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    os.link(directory / "app.py", directory / "alias.py")
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/demo")


def test_reject_fifo_without_blocking(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    os.mkfifo(directory / "pipe")
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/demo")
    with pytest.raises(FixtureError):
        read_project_file(tmp_path, "fixtures/demo/pipe")


def test_reject_oversize_and_empty_fixture(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    (directory / "app.py").write_bytes(b"x" * 1_048_577)
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/demo")
    (directory / "app.py").unlink()
    with pytest.raises(FixtureError):
        snapshot_fixture(tmp_path, "fixtures/demo")


def test_nested_files_and_size_limit(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    (directory / "nested").mkdir()
    (directory / "nested" / "data.txt").write_bytes(b"data")
    assert read_project_file(tmp_path, "fixtures/demo/nested/data.txt") == b"data"
    assert len(snapshot_fixture(tmp_path, "fixtures/demo").files) == 2
    with pytest.raises(FixtureError):
        read_project_file(tmp_path, "fixtures/demo/nested/data.txt", limit=2)


def test_directory_entry_limit(tmp_path: Path) -> None:
    directory = fixture_tree(tmp_path)
    for index in range(256):
        (directory / f"entry-{index}").touch()
    with pytest.raises(FixtureError, match="too many entries"):
        snapshot_fixture(tmp_path, "fixtures/demo")
