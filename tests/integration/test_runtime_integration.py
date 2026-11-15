"""Real AF-009 commands; requires an approved pinned image with checker tools."""

import hashlib
import json

import pytest
from test_sandbox_integration import sandbox  # noqa: F401 -- shared explicit opt-in fixture

from agentforge.core.fixtures import FixtureFile, FixtureSnapshot
from agentforge.sandbox.runner import SandboxRunner


def command_fixture(check: str, broken: bool) -> FixtureSnapshot:
    if check == "unit_tests":
        name = "test_owned.py"
        source = (
            "import unittest\nclass Owned(unittest.TestCase):\n"
            f"    def test_owned(self):\n        self.assertEqual(1, {2 if broken else 1})\n"
        )
    elif check == "lint":
        name, source = "owned.py", "import os\n" if broken else "value = 1\n"
    elif check == "typecheck":
        name, source = "owned.py", 'value: int = "bad"\n' if broken else "value: int = 1\n"
    else:
        name = "setup.py"
        source = (
            'raise RuntimeError("owned build failure")\n'
            if broken
            else (
                "from setuptools import setup\n"
                'setup(name="owned", version="0.0.1", py_modules=[])\n'
            )
        )
    content = source.encode()
    manifest = [(name, hashlib.sha256(content).hexdigest())]
    digest = (
        "sha256:" + hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()
    )
    return FixtureSnapshot(digest, (FixtureFile(name, content),))


@pytest.mark.parametrize("check", ["unit_tests", "lint", "typecheck", "build"])
def test_real_runtime_check(sandbox: SandboxRunner, check: str) -> None:  # noqa: F811
    passed = sandbox.run(command_fixture(check, False), check)
    assert passed.check == check and passed.status == "completed"
    assert passed.exit_code == 0, (passed.stdout, passed.stderr)
    failed = sandbox.run(command_fixture(check, True), check)
    assert failed.status == "completed" and failed.exit_code != 0
    assert failed.command_id != passed.command_id
