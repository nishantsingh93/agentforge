"""Operator verification using the already approved local Docker configuration."""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from agentforge.sandbox.runner import SandboxConfig

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "runs/local-sandbox-setup/20261109T174139780721Z/settings.json"
EXPECTED = {
    "test_real_isolation_and_repeat_runs",
    "test_real_timeout_and_verified_cleanup",
    "test_real_sandbox_output_is_sanitized_and_replayable",
    "test_real_gateway_checks_and_audit",
}


def verified(xml_path: Path) -> bool:
    try:
        cases = ET.parse(xml_path).findall(".//testcase")
        return (
            len(cases) == 4
            and {case.attrib.get("name") for case in cases} == EXPECTED
            and all(
                case.find("skipped") is None
                and case.find("failure") is None
                and case.find("error") is None
                for case in cases
            )
        )
    except (OSError, ET.ParseError):
        return False


def main() -> int:
    settings = json.loads(SETTINGS.read_text())
    host = settings["AGENTFORGE_TEST_DOCKER_HOST"]
    image = settings["AGENTFORGE_TEST_IMAGE"]
    SandboxConfig(host, image)  # Reuse existing local-socket/digest validation.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "docs/verification" / f"AF-008-real-{stamp}"
    output.mkdir()
    xml_path = output / "integration.xml"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration/test_sandbox_integration.py",
        "-ra",
        "-k",
        " or ".join(sorted(EXPECTED)),
        f"--junitxml={xml_path}",
    ]
    environment = dict(os.environ)
    environment.update(AGENTFORGE_TEST_DOCKER_HOST=host, AGENTFORGE_TEST_IMAGE=image)
    result = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180
    )
    log = result.stdout + result.stderr
    (output / "pytest.log").write_text(log)
    passed = result.returncode == 0 and verified(xml_path)
    (output / "result.json").write_text(
        json.dumps(
            {
                "command": command,
                "pytest_exit_code": result.returncode,
                "verified": passed,
                "settings_source": str(SETTINGS),
            },
            indent=2,
        )
        + "\n"
    )
    print(log)
    print(f"Evidence: {output}")
    print("VERIFIED: 4 passed, zero skipped" if passed else "NOT VERIFIED: inspect saved log")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
