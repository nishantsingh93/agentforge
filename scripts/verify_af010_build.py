"""Build a disposable source copy, avoiding concurrent workers' build directories."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="agentforge-af010-") as directory:
    copy = Path(directory)
    shutil.copytree(
        root / "src", copy / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info")
    )
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(root / name, copy / name)
    command = [sys.executable, "-m", "build"]
    environment = dict(
        os.environ, PIP_NO_INDEX="1", PIP_FIND_LINKS="/private/tmp/agentforge-wheels"
    )
    result = subprocess.run(command, cwd=copy, env=environment, text=True, capture_output=True)
    record = {
        "command": command,
        "cwd": str(copy),
        "environment_overrides": {
            "PIP_NO_INDEX": "1",
            "PIP_FIND_LINKS": "/private/tmp/agentforge-wheels",
        },
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    (root / "docs/verification/AF-010-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(result.stdout[-1500:])
    print(result.stderr)
    sys.exit(result.returncode)
