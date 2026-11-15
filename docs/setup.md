# Setup and offline smoke

Install the full source checkout following [contributing](contributing.md).
The benchmark and proposal-only adapter demo need no Docker. Scenario execution
requires an explicitly selected, reviewed local Linux-container Docker daemon.
No real production endpoint or model credential is needed or supported by the CLI.

## Configure a disposable Docker environment

Use a dedicated local environment with no sensitive host data or credentials.
On macOS, the existing optional `scripts/setup_local_sandbox.py` helper provisions
an isolated Colima profile; it installs software and pulls a public image, so review
[its scope](local-sandbox-setup.md) before deliberately running it. It is not part of
package installation. On Linux, install/configure Docker through your normal operator
process; never weaken socket permissions or use a shared production daemon.

The existing tool-image provisioning helper requires a reviewed local base image.
For a new local setup, these are explicit operator provisioning actions with network
access; fixture execution itself remains network-disabled:

```sh
export AGENTFORGE_TEST_DOCKER_HOST=unix:///var/run/docker.sock
export AGENTFORGE_TEST_IMAGE=python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
mkdir -p runs/setup
docker --host "$AGENTFORGE_TEST_DOCKER_HOST" pull "$AGENTFORGE_TEST_IMAGE"
python -c 'import json, os; from pathlib import Path; Path("runs/setup/base.json").write_text(json.dumps({k: os.environ[k] for k in ("AGENTFORGE_TEST_DOCKER_HOST", "AGENTFORGE_TEST_IMAGE")}))'
python scripts/provision_af009.py --settings runs/setup/base.json --verify
```

The example Unix socket is the common Linux location; macOS/rootless setups must
use their actual canonical local socket. Do not copy this workstation's socket or
locally built image ID to another machine. The base digest and tool pins are fixed
in the reviewed Dockerfile; unavailable architecture or stale pins must be reviewed,
not silently changed. The helper prints a **new settings.json path** and verifies
runtime tools. Read that file to set the test socket and newly built `sha256:...`
image ID, then run all integration tests from the contributor guide. The helper's
own eight-test check is not the entire integration suite.

## Run F01/F04 and render reports

After selecting the newly provisioned settings values:

```sh
export AGENTFORGE_DOCKER_HOST="$AGENTFORGE_TEST_DOCKER_HOST"
export AGENTFORGE_IMAGE="$AGENTFORGE_TEST_IMAGE"
python -m agentforge run --suite smoke --offline
```

The correct offline smoke exits **4** (inconclusive semantic evaluation), with
Bullseye outcomes and UNKNOWN judge scores. In a script, check specifically for 4;
do not use `|| true`, which would hide infrastructure failures. A deliberately
flawed demo should exit 1:

```sh
python -m agentforge run --scenario F04 --agent demo-patcher-flawed --offline
```

The run prints `Summary: runs/suite-.../summary.json`. Use that suite ID below:

```sh
python -m agentforge report suite-ID --format html > runs/report.html
python -m agentforge report suite-ID --format json > runs/report.json
python -m agentforge compare baseline-suite-ID current-suite-ID > runs/comparison.json
```

Replace IDs with observed output; do not overwrite any input artifact. Reports need
no live Docker daemon. Preserve the full run directories for digest-linked evidence.
There is no publish/deploy command. F05/F08 and other seeds have tested Python
oracles/simulator behavior; the shipped scripted CLI adapter repairs F01/F04 only.
The broader five-step v0.1 product demo is not fully exposed through this CLI.

## Troubleshooting

- Missing dependencies or setuptools: use the approved package index/cache and
  rerun install/build. Old archives do not verify changed source.
- Docker preflight fails: check the explicitly selected local socket, Linux daemon,
  reviewed image availability and exact digest. Do not retry through another daemon.
- Integration skips: supply the explicit test settings and require zero skips.
- Cleanup uncertain: retain the named `agentforge-...` container ID and stop runs;
  have the operator inspect only that disposable resource. Do not globally prune.
- Unknown model provider: use `--offline`; the CLI has no network provider transport.
- Claim says PASS but verdict is UNKNOWN/FAIL: inspect actual commands, oracles,
  hashes and policy events. A claim or model score cannot override these observations.
