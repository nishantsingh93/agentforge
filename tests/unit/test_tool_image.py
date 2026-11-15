"""Tool lock construction, no Docker or package execution."""

import hashlib
import runpy
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

LOCK_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/tool-image/lock_wheels.py"
lock_wheels = cast(Callable[[Path], str], runpy.run_path(str(LOCK_SCRIPT))["lock_wheels"])


def wheel(path: Path, name: str = "owned", version: str = "1.0") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("owned.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n")


def test_lock_exact_hash_and_version(tmp_path: Path) -> None:
    artifact = tmp_path / "owned.whl"
    wheel(artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert lock_wheels(tmp_path) == f"owned==1.0 --hash=sha256:{digest}\n"


def test_vendored_metadata_does_not_identify_wheel(tmp_path: Path) -> None:
    artifact = tmp_path / "owned.whl"
    wheel(artifact)
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr(
            "owned/_vendor/dependency-2.0.dist-info/METADATA",
            "Name: dependency\nVersion: 2.0\n",
        )
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert lock_wheels(tmp_path) == f"owned==1.0 --hash=sha256:{digest}\n"


@pytest.mark.parametrize("root_count", [0, 2])
def test_missing_or_ambiguous_root_metadata_rejected(tmp_path: Path, root_count: int) -> None:
    with zipfile.ZipFile(tmp_path / "owned.whl", "w") as archive:
        archive.writestr(
            "owned/_vendor/dependency.dist-info/METADATA", "Name: dependency\nVersion: 2.0\n"
        )
        for index in range(root_count):
            archive.writestr(
                f"owned{index}.dist-info/METADATA", f"Name: owned{index}\nVersion: 1.0\n"
            )
    with pytest.raises(ValueError, match="ambiguous wheel metadata"):
        lock_wheels(tmp_path)


@pytest.mark.parametrize("fault", ["empty", "duplicate", "nonwheel", "invalid-name"])
def test_bad_lock_inputs_rejected(tmp_path: Path, fault: str) -> None:
    if fault != "empty":
        wheel(tmp_path / "owned.whl", "--bad" if fault == "invalid-name" else "owned")
    if fault == "duplicate":
        wheel(tmp_path / "second.whl")
    if fault == "nonwheel":
        (tmp_path / "unexpected.txt").write_text("not a wheel")
    with pytest.raises(ValueError):
        lock_wheels(tmp_path)
