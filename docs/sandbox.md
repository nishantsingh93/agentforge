# Local disposable sandbox

The runner is implemented under `agentforge.sandbox` and wired through the gateway.
See [setup](setup.md) to configure your environment and run actual integration
checks. A skipped test is not containment evidence. There is no fallback to host
execution.

## Operator prerequisites

Use a disposable local Linux-container Docker environment with a reviewed Python
image already available by immutable digest. The image must provide
`/usr/local/bin/python`, stdlib unittest, Linux utilities/runtime, no declared
volumes and no baked-in credentials. The runner does not install Docker, pull an
image, configure a daemon, use remote endpoints, or use production credentials.
Only owned synthetic fixtures are in scope. Docker control itself is privileged;
do not regard containers as a universal boundary against adversarial code.

The integration tests read two explicit operator settings:

- `AGENTFORGE_TEST_DOCKER_HOST`: a canonical `unix:///absolute/path/to/socket`.
- `AGENTFORGE_TEST_IMAGE`: reviewed `image-name@sha256:<64 lowercase hex digits>`
  matching a local RepoDigests entry, or an exact locally built `sha256:<64 hex>`
  image ID matching inspect Id. Mutable tags are rejected.

With those configured, run:

```sh
.venv/bin/python -m pytest tests/integration/test_sandbox_integration.py -ra
```

Without Docker or these settings, tests explicitly skip. With settings present,
daemon/image failures fail the tests. Never count a skip as containment evidence.

## Boundary and lifecycle

`SandboxRunner(SandboxConfig(...)).run(snapshot, "unit_tests")` is an **internal**
executor primitive. The trusted gateway/executor invokes it for agent requests;
adapters must never bypass that gateway. This API itself does not grant authorization.

The runner revalidates all fixture paths, sizes, duplicates, file/directory
collisions and content digest, then sends bounded base64 JSON over stdin. A trusted
bootstrap independently validates paths/sizes/digest and materializes only regular
files in an empty container `/workspace`. No archive extraction, source imports
on the host or host directory mounts. It discovers `test*.py` with unittest inside
the container; zero tests is an error. The fixture is untrusted and can influence
its test output, so a zero exit is execution evidence, not an independent oracle
or policy authorization. The bootstrap itself is never executed on the host.

The container uses an explicit local socket and empty temporary Docker config;
no inherited host credentials, proxy variables or Docker context. Read-only root,
nonroot UID/GID 65532, dropped capabilities, no-new-privileges and default seccomp
apply. Network and IPC are disabled; `/workspace` is a 64 MiB noexec tmpfs.
CPU/memory/PID limits are 1 CPU, 256 MiB (no additional swap), and 64 processes.
No Docker log persistence (`--log-driver none`) or default shared-memory mount
(`--ipc none`). These two restrictive additions prevent unbounded daemon logs and
an extra writable shared-memory area; they do not relax the approved profile.

Host transport bounds input to 12 MB, each output stream to 1 MiB, and fixture
execution to 1–60 seconds. Preflight and cleanup calls each have 5-second limits.
Pipes are drained concurrently; output-limit or timeout events terminate the CLI
process and trigger container cleanup. Returned ToolResult preserves actual exit
code and captured output; `error` may include truncated output, never a fabricated
success transcript. Invalid UTF-8 is represented with replacement characters.

Cleanup targets only the generated `agentforge-<uuid>` name. An independent
successful `docker ps -a` query must establish absence. Interrupted startup also
requires acknowledged removal to avoid treating an in-flight creation as cleaned
up. Uncertain cleanup raises SandboxCleanupError with the container name; retain
it for operator investigation. No global prune or unrelated resource deletion.

## Evidence and limitations

Unit tests cover flags, missing capabilities, rejected inputs, timeout/output
limits, explicit cleanup failures, unique names, and absence of inherited synthetic
environment values. Fixed trusted subprocess snippets test pipe handling on the
host; they are not fixture execution or an isolation fallback.

The real test suite checks UID, fresh workspaces across runs, inaccessible synthetic
host markers, protected paths, Docker socket absence, loopback-only networking,
resource limits, timeout and verified cleanup. Fixture scripts are stored as
`.py.txt` data so pytest cannot import them on the host. No production secrets are
probed. Run these checks against the platform and image you intend to use, and
retain the actual results with your evaluation evidence.

The daemon, reviewed image, container kernel/runtime and trusted caller remain
assumptions. A malicious daemon can lie about metadata/state; a kernel vulnerability
may defeat isolation. No general safety guarantee is claimed. Docker installation and image provisioning are separate operator actions.
