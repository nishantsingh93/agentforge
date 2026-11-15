# AF-004 sandbox implementation proposal — approved

The user approved this scope on 2026-11-09. The design below is retained as the
approval record; implementation/testing status is in `docs/tickets/AF-004.md`.

Approval scope: implement the local disposable Docker runner, its owned test
fixtures, unit/integration tests and documentation described here. No changes to
dependencies, CI, Docker installation/daemon configuration, cloud infrastructure,
policy/approval engine or real production integrations. This is a reviewable design
proposal; no sandbox runtime source has been applied or executed.

## Files and ownership

| File | Proposed change |
| --- | --- |
| `src/agentforge/sandbox/__init__.py` | New internal executor package; not exported as an agent tool |
| `src/agentforge/sandbox/runner.py` | Typed Docker configuration, availability checks, bounded process lifecycle and typed result |
| `src/agentforge/sandbox/bootstrap.py` | Owned Python bootstrap sent to the container; validates/materializes snapshot bytes only under `/workspace` |
| `tests/unit/test_sandbox.py` | Injected Docker transport/clock tests; no host fixture execution |
| `tests/integration/test_sandbox.py` | Real Docker isolation, timeout, cleanup and repeat-run checks; explicitly skipped with reason when unavailable |
| `tests/fixtures/sandbox/` | Owned small unittest payloads and synthetic containment probes; never imported/executed on host |
| `docs/sandbox.md` | Local setup assumptions, threat model, test commands, residual risks and cleanup behavior |

## Interface and data flow

`SandboxRunner` receives trusted operator configuration: explicit local Unix
Docker socket, an already present reviewed Python image referenced by immutable
SHA256 digest, and timeout (bounded 1–60 seconds). No image pull/build is performed
automatically. No Docker SDK dependency is needed: use argument-array subprocess
calls (`shell=False`) to the discovered Docker CLI.

The runner accepts an AF-003 `FixtureSnapshot` plus an allowlisted check identifier
(`unit_tests` initially), not shell text or arbitrary host commands. Revalidate
snapshot paths, duplicate names, digest and sizes at entry; do not assume callers
constructed a valid dataclass. Transfer file bytes as bounded base64 JSON on stdin.
No tar extraction and no host mounts. A trusted bootstrap writes regular files in
an initially empty container-only workspace, then invokes the fixed Python unittest
command inside the container. Treat all fixture output as untrusted data.

AF-004 is an internal execution primitive tested with owned fixtures. Do not expose
it to agent adapters or add a CLI `run` bypass. Agent-originated actions will be
wired only through AF-008's approved gateway. Direct internal availability tests
and owned integration probes are the only AF-004 callers.

## Exact required container settings

Construct an argv list with this profile; interpolated fields below are validated
operator inputs or generated names, never scenario-supplied options:

```text
docker --host <explicit-local-unix-socket> --config <empty-temporary-config-dir>
  run --rm --pull never --name agentforge-<generated-uuid>
  --label agentforge.disposable=true
  --network none --read-only --user 65532:65532
  --cap-drop ALL --security-opt no-new-privileges=true
  --pids-limit 64 --memory 256m --memory-swap 256m --cpus 1
  --ulimit nofile=256:256 --ulimit core=0:0
  --tmpfs /workspace:rw,nosuid,nodev,noexec,size=64m,uid=65532,gid=65532,mode=0700
  --workdir /workspace --no-healthcheck
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/workspace/tmp
  --entrypoint /usr/local/bin/python -i
  <reviewed-image>@sha256:<64-lowercase-hex> -I -c <owned-bootstrap-source>
```

The `-i` above is a Docker option (keep stdin open), before the image; `-I` is a
Python option after the image. No published ports, devices, host namespaces,
privileged flags, bind mounts, named volumes, Docker socket mounts or inherited
host environment. Retain Docker's default seccomp profile. Inspect the chosen
image and reject declared volumes; otherwise Docker could create unrequested
mounts. Use a reviewed Python image whose defaults contain no credentials.

Do not inherit Docker context, credential configuration, DOCKER_HOST or arbitrary
environment values. Pass the chosen local socket explicitly and an empty temporary
Docker config directory. Reject remote TCP/SSH endpoints. This limits the tool to
the intended local disposable environment; it is not permission to reconfigure it.

## Lifecycle, limits and failure behavior

1. Check CLI, explicit local daemon and pinned local image with bounded commands.
   Any missing capability means `SandboxUnavailable`; do not execute on the host.
2. Generate a unique name; execute only this container. Bound stdin size, wall time
   and collected stdout/stderr (1 MiB each). Stream/drain output with a deadline;
   do not buffer unlimited output in the host process.
3. Return observed exit code, duration, stdout/stderr and completed/timeout/error
   status through the existing ToolResult contract. A textual success message
   cannot establish successful execution or a passed oracle.
4. In all exit paths, clean only the exact generated container using bounded
   `docker rm --force <generated-name>` if necessary, and verify it is absent.
   Never issue global prune, broad name matching, or delete unrelated resources.
   Cleanup/daemon failure is an infrastructure error with an unresolved container
   reference; never report cleanup success without observation.
5. Remove only runner-created temporary config data. No fixture source writes.

## Required tests and acceptance evidence

- Unit spies: missing CLI/daemon/image makes no execution call; invalid image,
  remote socket, traversal, duplicate paths and unsupported check rejected.
- Assert exact confinement flags and absence of mounts/host environment/unsafe
  options; timeout, output limit and failed cleanup are explicit errors.
- Real containers: two runs have different workspaces and no shared mutations;
  owned test passes; attempted outbound network fails; synthetic host marker is
  inaccessible; `/etc` writes fail; no Docker socket; nonroot UID observed.
- Real timeout is terminated and container absence independently verified.
- Test memory/process configuration by inspection and controlled bounded probes.
- Do not label mocked isolation tests as real containment evidence. Missing Docker
  integration tests keep AF-004 incomplete and dependent tickets blocked.

## Risk assessment and rollback

Docker control is privileged on many installations. Containers share a kernel and
are not a universal boundary against hostile code. Even after tests pass, use only
owned synthetic fixtures in a disposable local environment without sensitive host
access. A compromised daemon/image or kernel escape is outside the claimed v0.1
guarantees. No production credentials are needed or accessed.

Implementation can be reverted by removing the listed new module/tests/docs.
Runtime cleanup touches only uniquely named runner-created containers. Approval
does not include installing Docker, pulling an image, altering host permissions,
or asserting a completed security review. Those environmental prerequisites remain
explicit. This machine currently has no `docker` executable.

Design references checked 2026-11-09:
[Docker run reference](https://docs.docker.com/engine/containers/run/) and
[Docker Engine security](https://docs.docker.com/engine/security/).
