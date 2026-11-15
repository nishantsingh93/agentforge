"""Verify AF-014 CLI orchestration using the existing approved Docker tool image."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from agentforge.sandbox.runner import SandboxConfig

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "runs/tool-image/20261111T043952065408Z/settings.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=SETTINGS)
    settings_path = parser.parse_args().settings.resolve()
    settings = json.loads(settings_path.read_text())
    SandboxConfig(settings["AGENTFORGE_TEST_DOCKER_HOST"], settings["AGENTFORGE_TEST_IMAGE"])
    output = (
        ROOT
        / "docs/verification"
        / ("AF-014-real-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    output.mkdir()
    xml_path = output / "integration.xml"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration/test_run_integration.py",
        "-ra",
        f"--junitxml={xml_path}",
    ]
    environment = dict(os.environ)
    environment.update(
        {key: settings[key] for key in ("AGENTFORGE_TEST_DOCKER_HOST", "AGENTFORGE_TEST_IMAGE")}
    )
    result = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180
    )
    log = result.stdout + result.stderr
    (output / "pytest.log").write_text(log)
    cases = ET.parse(xml_path).findall(".//testcase") if xml_path.exists() else []
    expected = {"test_real_cli_smoke", "test_real_cli_repeatability", "test_real_cli_flawed_demo"}
    verified = (
        result.returncode == 0
        and len(cases) == 3
        and {case.attrib.get("name") for case in cases} == expected
        and all(not list(case) for case in cases)
    )
    (output / "result.json").write_text(
        json.dumps(
            {
                "command": command,
                "exit_code": result.returncode,
                "verified": verified,
                "settings_source": str(settings_path),
            },
            indent=2,
        )
        + "\n"
    )
    print(log)
    print(f"Evidence: {output}")
    print("VERIFIED: 3 passed, zero skipped" if verified else "NOT VERIFIED: inspect saved log")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
