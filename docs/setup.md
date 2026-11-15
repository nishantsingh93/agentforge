# Local setup and first evaluation

Install the full source checkout using the [README](../README.md#get-started).
Scenario execution requires Python 3.12+ and a dedicated local Docker daemon
running Linux containers. The benchmark and proposal-only demo do not need Docker.

## 1. Select your local Docker socket

Use a disposable development environment without sensitive data. Docker installation
is managed separately through your platform's normal setup process. Do not select
a shared production daemon or change socket permissions to bypass an access error.

On Linux, a common socket is:

```sh
export AGENTFORGE_DOCKER_HOST=unix:///var/run/docker.sock
```

On macOS or rootless Linux, use the actual local Unix socket for your dedicated
Docker environment. Resolve symlinks to the canonical socket path. AgentForge
requires an explicit local socket; it does not silently use your current context.

```sh
docker --host "$AGENTFORGE_DOCKER_HOST" info
```

Verify that this is your intended local Linux-container daemon before continuing.

## 2. Build the tooling image

From the repository root:

```sh
mkdir -p runs/setup/docker-config
docker --host "$AGENTFORGE_DOCKER_HOST" --config "$PWD/runs/setup/docker-config" build \
  --iidfile "$PWD/runs/setup/image-id.txt" scripts/tool-image
export AGENTFORGE_IMAGE="$(cat runs/setup/image-id.txt)"
```

The Dockerfile pins its base image and tooling versions. Its wheel-lock helper
records hashes and installs the resolved artifacts using those hashes. Building
needs network access to fetch public packages; fixture execution is network-disabled.
The resulting `sha256:…` image ID is the immutable local identity used for runs.
Keep the ID with your results. Runtime preflight verifies the selected image and
never pulls a replacement or installs missing tools.

If the base image is unavailable for your architecture, stop and review the image
requirements. Do not replace a pinned identity with an arbitrary mutable tag.

## 3. Run a correct smoke evaluation

```sh
python -m agentforge run --suite smoke --offline
```

Expected: F01/F04 Bullseye outcomes, quality INCOMPLETE, final UNKNOWN, exit **4**.
Offline judges have no semantic model evidence. Exit 4 is intentional; an error
from Docker is exit 3 and should be investigated separately.

## 4. Run the deliberately flawed adapter

```sh
python -m agentforge run --scenario F04 --agent demo-patcher-flawed --offline
```

Expected: test-integrity violation, Misleading outcome, final FAIL, exit **1**.
The test change happens in the disposable fixture, not your checkout.

## 5. Inspect the report

Copy the suite ID printed by the command, replacing `YOUR_SUITE_ID`:

```sh
python -m agentforge report YOUR_SUITE_ID --format html > runs/report.html
python -m agentforge report YOUR_SUITE_ID --format json > runs/report.json
```

Open the HTML file in your browser. Preserve the source run directory for trace
and digest-linked evidence. Reports can be rendered after Docker is stopped.

## 6. Verify your installation with real integrations

```sh
export AGENTFORGE_TEST_DOCKER_HOST="$AGENTFORGE_DOCKER_HOST"
export AGENTFORGE_TEST_IMAGE="$AGENTFORGE_IMAGE"
python -m pytest tests/integration -ra
```

Require zero skips when claiming real integration verification. Without explicit
test settings Docker tests skip; with settings present but unavailable, they fail.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker preflight fails | Explicit canonical local socket, daemon availability, Linux containers and image ID. |
| Required tool is missing | Build the tooling Dockerfile; a plain Python image lacks the fixture tools. |
| Integration tests skip | Set both `AGENTFORGE_TEST_*` variables. |
| Final decision is UNKNOWN | Expected in offline mode; inspect observed outcomes and checks separately. |
| Unsupported scenario/agent | CLI patch demos cover F01/F04; use the Python API for custom adapters. |
| Cleanup is uncertain | Stop new runs and inspect only the named disposable container; do not globally prune. |

See [run semantics](runs.md), [reporting](reporting.md) and [security boundaries](security.md).
