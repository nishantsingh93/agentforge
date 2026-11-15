"""Owned bootstrap source, sent to Docker; never executed on the host."""

BOOTSTRAP = r"""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import unittest

raw = sys.stdin.buffer.read(12_000_001)
if len(raw) > 12_000_000:
    raise ValueError("payload too large")
payload = json.loads(raw)
if set(payload) != {"digest", "files"}:
    raise ValueError("invalid payload")
files = payload["files"]
if not isinstance(files, list) or not 1 <= len(files) <= 256:
    raise ValueError("invalid file count")
validated = []
seen = set()
total = 0
for entry in files:
    if not isinstance(entry, dict) or set(entry) != {"path", "content"}:
        raise ValueError("invalid file")
    name = entry["path"]
    if not isinstance(name, str) or len(name) > 4096:
        raise ValueError("invalid path")
    parts = name.split("/")
    if (any(p in {"", ".", ".."} for p in parts) or len(parts) > 17
        or "\\" in name or ":" in name or any(ord(c) < 32 for c in name)
        or name in seen):
        raise ValueError("unsafe path")
    seen.add(name)
    content = base64.b64decode(entry["content"], validate=True)
    total += len(content)
    if len(content) > 1_048_576 or total > 8_388_608:
        raise ValueError("fixture too large")
    validated.append((name, content))
validated.sort()
manifest = [(name, hashlib.sha256(content).hexdigest()) for name, content in validated]
digest = "sha256:" + hashlib.sha256(json.dumps(
    manifest, ensure_ascii=True, separators=(",", ":")
).encode()).hexdigest()
if digest != payload["digest"]:
    raise ValueError("fixture digest mismatch")
root = Path("/workspace")
if list(root.iterdir()):
    raise ValueError("workspace not empty")
for name, content in validated:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(content)
(root / "tmp").mkdir(exist_ok=True)
os.chdir(root)
sys.dont_write_bytecode = True
check = sys.argv[1]
if check != "unit_tests":
    commands = {
        "lint": ["ruff", "check", "--isolated", "--no-cache", "."],
        "typecheck": ["mypy", "--strict", "--config-file=/dev/null",
                      "--cache-dir=/workspace/tmp/mypy", "."],
        "build": ["build", "--no-isolation", "."],
    }
    if check not in commands:
        raise ValueError("unsupported check")
    # -I prevents fixture modules shadowing the installed checker. Explicit lint
    # and type config prevents fixture plugins/excludes from changing the check.
    # Build backends remain untrusted fixture execution inside this container.
    result = subprocess.run([sys.executable, "-I", "-m", *commands[check]],
                            env={"PATH": os.defpath, "TMPDIR": "/workspace/tmp",
                                 "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_INDEX": "1"},
                            check=False)
    sys.exit(result.returncode)
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root), pattern="test*.py")
if suite.countTestCases() == 0:
    raise ValueError("fixture contains no tests")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
