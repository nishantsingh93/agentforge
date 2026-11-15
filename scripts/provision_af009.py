"""Approved local image provisioning. No fixture data or host credentials in build."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from agentforge.sandbox.runner import SandboxConfig

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "runs/local-sandbox-setup/20261109T174139780721Z/settings.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="run all eight integration checks")
    options = parser.parse_args()
    settings = json.loads(SETTINGS.read_text())
    original = SandboxConfig(
        settings["AGENTFORGE_TEST_DOCKER_HOST"], settings["AGENTFORGE_TEST_IMAGE"]
    )
    output = ROOT / "runs/tool-image" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    records: list[dict[str, object]] = []
    docker = shutil.which("docker")
    if docker is None:
        print("Docker unavailable; no host fallback")
        return 1

    def invoke(args: list[str], timeout: float = 30) -> str:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": os.defpath, "LC_ALL": "C"},
        )
        records.append(
            {
                "command": args,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        (output / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
        if result.returncode != 0:
            raise RuntimeError("command failed; inspect commands.json")
        return result.stdout

    try:
        with tempfile.TemporaryDirectory(prefix="af009-docker-") as temporary:
            prefix = [docker, "--host", original.docker_host, "--config", temporary]
            if invoke([*prefix, "info", "--format", "{{.OSType}}"]).strip() != "linux":
                raise ValueError("Linux daemon required")
            # The context contains only reviewed provisioning sources, never fixtures.
            context = Path(temporary) / "context"
            context.mkdir()
            for name in ("Dockerfile", "lock_wheels.py"):
                shutil.copy2(ROOT / "scripts/tool-image" / name, context / name)
            image_file = output / "image-id.txt"
            invoke(
                [*prefix, "build", "--pull=false", "--iidfile", str(image_file), str(context)], 600
            )
            image_id = image_file.read_text().strip()
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
                raise ValueError("build did not return an immutable image ID")
            metadata = json.loads(invoke([*prefix, "image", "inspect", image_id]))
            if (
                len(metadata) != 1
                or metadata[0]["Id"] != image_id
                or metadata[0]["Os"] != "linux"
                or metadata[0]["Config"].get("Volumes")
            ):
                raise ValueError("invalid built image metadata")
            lock = invoke(
                [
                    *prefix,
                    "run",
                    "--rm",
                    "--pull",
                    "never",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "65532:65532",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges=true",
                    "--entrypoint",
                    "/usr/local/bin/python",
                    image_id,
                    "-I",
                    "-c",
                    (
                        "from pathlib import Path; "
                        "print(Path('/opt/agentforge/tools.lock').read_text(), end='')"
                    ),
                ]
            )
            (output / "tools.lock").write_text(lock)
            (output / "image-inspect.json").write_text(json.dumps(metadata, indent=2) + "\n")
            new_settings = {
                "AGENTFORGE_TEST_DOCKER_HOST": original.docker_host,
                "AGENTFORGE_TEST_IMAGE": image_id,
            }
            SandboxConfig(original.docker_host, image_id)
            (output / "settings.json").write_text(json.dumps(new_settings, indent=2) + "\n")
        print(f"Provisioned settings: {output / 'settings.json'}", flush=True)
        if options.verify:
            import sys

            command = [
                sys.executable,
                str(ROOT / "scripts/verify_af009.py"),
                "--settings",
                str(output / "settings.json"),
            ]
            result = subprocess.run(
                command,
                cwd=ROOT,
                env={"PATH": str(Path(docker).parent) + os.pathsep + os.defpath, "LC_ALL": "C"},
                check=False,
            )
            (output / "verification.json").write_text(
                json.dumps({"command": command, "exit_code": result.returncode}, indent=2) + "\n"
            )
            return result.returncode
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        (output / "failure.txt").write_text(str(error) + "\n")
        print(f"Provisioning incomplete. Evidence: {output}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
