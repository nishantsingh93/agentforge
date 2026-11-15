"""Internal storage tests use synthetic nonsensitive bytes only."""

from pathlib import Path

import pytest

from agentforge.core.artifacts import ArtifactError, ArtifactStore, digest_bytes


def test_content_address_and_duplicate_are_immutable(tmp_path: Path) -> None:
    with ArtifactStore(tmp_path, "run-1") as store:
        digest = store.put(b"synthetic evidence")
        assert digest == digest_bytes(b"synthetic evidence")
        assert store.put(b"synthetic evidence") == digest
        assert store.read(digest) == b"synthetic evidence"
        assert len(list((tmp_path / "run-1/objects").iterdir())) == 1
        assert store.put(b"different evidence") != digest
    with pytest.raises(ArtifactError, match="closed"):
        store.read(digest)


def test_existing_run_is_never_overwritten(tmp_path: Path) -> None:
    with ArtifactStore(tmp_path, "run-1") as first:
        first.put(b"original")
        with pytest.raises(FileExistsError):
            ArtifactStore(tmp_path, "run-1")
        assert first.read(digest_bytes(b"original")) == b"original"


@pytest.mark.parametrize("run_id", ["../escape", "/absolute", "", "a/b", ".hidden"])
def test_bad_run_ids_rejected(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ArtifactError):
        ArtifactStore(tmp_path, run_id)


def test_corruption_and_symlink_rejected(tmp_path: Path) -> None:
    with ArtifactStore(tmp_path, "run-1") as store:
        digest = store.put(b"original")
        path = tmp_path / "run-1/objects" / digest.removeprefix("sha256:")
        path.write_bytes(b"corrupted")
        with pytest.raises(ArtifactError, match="does not match"):
            store.read(digest)
        with pytest.raises(ArtifactError):
            store.put(b"original")
        assert not list(path.parent.glob(".tmp-*"))
        path.unlink()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.write_bytes(b"original")
        path.symlink_to(elsewhere)
        with pytest.raises(ArtifactError):
            store.read(digest)


def test_bad_digest_and_size(tmp_path: Path) -> None:
    with ArtifactStore(tmp_path, "run-1") as store:
        with pytest.raises(ArtifactError):
            store.read("../../elsewhere")
        with pytest.raises(ArtifactError):
            store.put(b"x" * 8_388_609)
        assert not list((tmp_path / "run-1/objects").iterdir())


def test_interrupted_publication_does_not_expose_partial_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_link(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic publication failure")

    with ArtifactStore(tmp_path, "run-1") as store:
        monkeypatch.setattr("agentforge.core.artifacts.os.link", broken_link)
        with pytest.raises(OSError, match="synthetic"):
            store.put(b"complete payload")
        assert not list((tmp_path / "run-1/objects").iterdir())
