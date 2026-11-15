"""Create a hash-pinned lock from the resolved Linux wheels inside the build."""

import hashlib
import re
import zipfile
from email.parser import BytesParser
from pathlib import Path


def lock_wheels(directory: Path) -> str:
    entries: dict[str, str] = {}
    for wheel in sorted(directory.iterdir()):
        if not wheel.name.endswith(".whl") or not wheel.is_file():
            raise ValueError("only wheel artifacts supported")
        with zipfile.ZipFile(wheel) as archive:
            # Vendored dependencies may include nested dist-info directories;
            # only the root dist-info identifies the wheel being locked.
            paths = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(paths) != 1:
                raise ValueError("ambiguous wheel metadata")
            metadata = BytesParser().parsebytes(archive.read(paths[0]))
        name, version = str(metadata["Name"]), str(metadata["Version"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version
        ):
            raise ValueError("invalid wheel identity")
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in entries:
            raise ValueError("duplicate package")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        entries[key] = f"{key}=={version} --hash=sha256:{digest}"
    if not entries:
        raise ValueError("empty wheel set")
    return "\n".join(entries[key] for key in sorted(entries)) + "\n"


if __name__ == "__main__":
    Path("/opt/agentforge/tools.lock").write_text(lock_wheels(Path("/opt/agentforge/wheels")))
