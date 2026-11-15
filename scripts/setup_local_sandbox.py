"""Operator-run macOS setup. Never run this to bypass a restricted agent session."""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT = Path(__file__).resolve().parents[1]
PROFILE = "agentforge"
IMAGE_TAG = "docker.io/library/python:3.12-slim-bookworm"
CONFIG: dict[str, Any] = {
    "cpu": 2,
    "memory": 2,
    "disk": 10,
    "arch": "aarch64",
    "vmType": "vz",
    "runtime": "docker",
    "mounts": None,
    "forwardAgent": False,
    "sshConfig": False,
    "autoActivate": False,
    "kubernetes": {"enabled": False},
    "network": {"address": False, "hostAddresses": False},
}


def validate_profile(config: dict[str, Any]) -> None:
    for key in (
        "cpu",
        "memory",
        "disk",
        "arch",
        "vmType",
        "runtime",
        "mounts",
        "forwardAgent",
        "sshConfig",
        "autoActivate",
    ):
        if key not in config or config[key] != CONFIG[key]:
            raise ValueError(f"existing dedicated profile has unexpected {key}; review it manually")
    if config.get("kubernetes", {}).get("enabled", False):
        raise ValueError("Kubernetes must be disabled")
    if config.get("provision") or config.get("env"):
        raise ValueError("unexpected provisioning or environment in dedicated profile")
    network = config.get("network", {})
    if network.get("address") or network.get("hostAddresses"):
        raise ValueError("unexpected network forwarding in dedicated profile")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only", action="store_true", help="Inspect prerequisites; do not modify anything"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("this setup is scoped to Apple Silicon macOS")
    if args.check_only:
        print(
            json.dumps(
                {name: shutil.which(name) for name in ("brew", "colima", "docker")}, indent=2
            )
        )
        return 0 if shutil.which("colima") and shutil.which("docker") else 2

    # Separate installation state from any existing Colima/default Docker environment.
    colima_home = Path.home() / ".colima-agentforge"
    config_path = colima_home / PROFILE / "colima.yaml"
    if config_path.exists():
        existing = yaml.safe_load(config_path.read_text())
        if not isinstance(existing, dict):
            raise ValueError("invalid dedicated profile")
        validate_profile(existing)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = PROJECT / "runs" / "local-sandbox-setup" / stamp
    output.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    environment = dict(os.environ)
    environment["COLIMA_HOME"] = str(colima_home)
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "SSH_AUTH_SOCK"):
        environment.pop(key, None)
    environment["HOMEBREW_NO_AUTO_UPDATE"] = "1"
    environment["HOMEBREW_NO_INSTALL_CLEANUP"] = "1"

    def command(argv: list[str], *, timeout: int = 1800) -> str:
        print("Running:", " ".join(argv), flush=True)
        logfile = output / f"command-{len(records) + 1:02}.log"
        with logfile.open("w") as log:
            try:
                completed = subprocess.run(
                    argv,
                    cwd=PROJECT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 124
        records.append({"argv": argv, "exit_code": code, "log": str(logfile)})
        (output / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
        text = logfile.read_text(errors="replace")
        print(text, flush=True)
        if code:
            raise RuntimeError(f"command failed ({code}); evidence: {logfile}")
        return text

    missing = [name for name in ("colima", "docker") if shutil.which(name) is None]
    if missing:
        brew = shutil.which("brew")
        if brew is None:
            raise RuntimeError("Homebrew is required; install it separately")
        command([brew, "install", *missing])
    colima = shutil.which("colima")
    docker = shutil.which("docker")
    if colima is None or docker is None:
        raise RuntimeError("installed tools must be on PATH")
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("x") as config_file:
            yaml.safe_dump(CONFIG, config_file, sort_keys=False)
    command([colima, "start", PROFILE, "--activate=false"])
    validate_profile(yaml.safe_load(config_path.read_text()))
    endpoint = "unix://" + str(colima_home / PROFILE / "docker.sock")
    with tempfile.TemporaryDirectory(prefix="agentforge-setup-docker-") as config_dir:
        prefix = [docker, "--host", endpoint, "--config", config_dir]
        command([*prefix, "info", "--format", "{{.OSType}}"], timeout=30)
        command([*prefix, "pull", IMAGE_TAG])
        metadata = json.loads(command([*prefix, "image", "inspect", IMAGE_TAG], timeout=30))[0]
        if metadata["Os"] != "linux" or metadata["Config"].get("Volumes"):
            raise RuntimeError("unexpected official image metadata")
        references = metadata.get("RepoDigests", [])
        pinned = next(
            (
                ref
                for ref in references
                if re.fullmatch(r"(?:docker.io/library/)?python@sha256:[a-f0-9]{64}", ref)
            ),
            None,
        )
        if pinned is None:
            raise RuntimeError("official Python image digest could not be confirmed")
        settings = {"AGENTFORGE_TEST_DOCKER_HOST": endpoint, "AGENTFORGE_TEST_IMAGE": pinned}
        (output / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
        environment.update(settings)
        junit = output / "integration.xml"
        command(
            [
                str(PROJECT / ".venv/bin/python"),
                "-m",
                "pytest",
                "tests/integration/test_sandbox_integration.py",
                "-ra",
                f"--junitxml={junit}",
            ],
            timeout=180,
        )
        report = ET.parse(junit).getroot()
        cases = list(report.iter("testcase"))
        if len(cases) < 2 or any(case.find("skipped") is not None for case in cases):
            raise RuntimeError(
                "integration evidence incomplete; skipped tests cannot pass this gate"
            )
        (output / "result.json").write_text(
            json.dumps(
                {
                    "status": "integration_passed_pending_review",
                    "test_cases": len(cases),
                    "image": pinned,
                    "docker_host": endpoint,
                },
                indent=2,
            )
            + "\n"
        )
    print(f"Integration evidence saved to {output}.")
    print("Tracker needs review before AF-004 is marked verified.")
    print(
        "Dedicated VM left running. Stop it with: "
        f"COLIMA_HOME='{colima_home}' colima stop {PROFILE}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Setup incomplete: {error}", file=sys.stderr)
        raise SystemExit(1) from error
