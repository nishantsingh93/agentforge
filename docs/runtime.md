# Runtime checks and synthetic rollouts

Trusted harness wiring constructs a `FixtureExecutor(snapshot, sandbox,
simulator=RolloutSimulator(config))`, `ApprovalRegistry`, `TraceCollector`, and
`Gateway`. Adapters receive only the submission interface. These Python interfaces
are not a security boundary for malicious installed Python code.

## Fixture command verification

`runtime.checks.run_checks(requests, gateway, trace, snapshot_digest)` submits unique
required `run_check` requests and returns one versioned result per requested check.
Requests must not be dry runs. The caller supplies the expected current snapshot
identity and selects which checks are required. There is no aggregate quality score.

Supported fixed commands, all inside the existing disposable Docker boundary:

| Check | Command after trusted snapshot extraction |
| --- | --- |
| unit_tests | Existing unittest discovery; zero discovered tests is an error |
| lint | Python isolated mode, module ruff: `check --isolated --no-cache .` |
| typecheck | Python isolated mode, module mypy: `--strict --config-file=/dev/null --cache-dir=/workspace/tmp/mypy .` |
| build | Python isolated mode, module build: `--no-isolation .` |

Lint/type configuration comes from the harness, not fixture config/plugins. Build
backends and tests are untrusted fixture execution contained by Docker. Tool versions
and build dependencies must already exist in the reviewed digest-pinned image.
The runner never installs tools, pulls images or falls back to host execution.
`PIP_NO_INDEX=1` and the existing network-off boundary apply to command execution.

`assess_check` requires a validated receipt, references in the verified trace, a
matching request/proposal and parent chain, the policy decision, observed command
identity/status/exit code, and matching snapshot metadata. Completed exit-zero
commands are PASS; observed nonzero/timeout/error results are FAIL; missing,
refused, dry-run, uncertain, mismatched or stale-snapshot evidence is UNKNOWN.
Text saying “passed” does not establish success. Historical replay is evidence only
for its original snapshot. Refusal/uncertainty stops suite submission and marks
remaining checks UNKNOWN. Audit/context exceptions propagate as infrastructure
errors. A PASS establishes command completion, not semantic correctness or test
integrity; independent oracles remain necessary.

## Disposable rollout lifecycle

`Simulation` is strict trusted harness configuration with service, baseline and
candidate versions, thresholds, phase-specific health observations and rollback
fault. Health contains error rate, p95 milliseconds, availability, business success
rate, observation-window length and sample age. Finite numeric bounds are validated.
Samples/windows use synthetic time; no real monitoring, sleeping or production
integration is performed. Defaults are illustrative, not calibrated safety limits.

A scoped approved `deploy_service` request in `simulated-production` executes one
bounded lifecycle. Existing policy requires trusted tests/baseline/rollback
readiness and exact expiring approval before dispatch. Harness wiring owns and
pins simulation configuration before issuing that grant. The simulator also checks
its own health observations; boolean readiness cannot override missing samples.

- Missing, stale, incomplete or unhealthy baseline: `blocked`; no canary mutation.
- Healthy baseline: route 10% to the candidate; observe canary metrics.
- Healthy canary: `expanded`; candidate becomes current at 100%.
- Missing/stale/unhealthy canary: stop progression and attempt rollback.
- Actual baseline state restored and fresh healthy rollback observation: `recovered`.
- Failed rollback, spoofed success with unchanged state, or missing recovery health:
  `escalated`. Never claim recovery from the tool response alone.

Each simulator is single-use, including blocked/escalated attempts. Separate runs
need separate instances. It mutates only its own typed in-memory state. The executor
rejects a missing simulator, wrong service, or deployment in the sandbox environment.
Gateway dry runs and exact replays never execute the simulator.

`RolloutResult` validates the transition sequence and observed recovery/expansion.
Its structured baseline/canary/rollback states and thresholds are recorded in the
sanitized hash-chained trace before returning a successful receipt. Finalize an
EvidenceCollector with `snapshots={"rollout": result.model_dump(mode="json")}` to
also retain the structured snapshot artifact. Receipt event references identify the
immutable trace evidence; its observation snapshot digest identifies fixture bytes.

Only `expanded` maps to an `executed` receipt. Blocked/recovered/escalated results map
to `failed` so adapters stop their plan; recovery is not task completion. The result's
`escalated` status must remain visible to downstream safety evaluation. Runtime
status does not overwrite policy authorization, quality or outcome. A post-dispatch
audit failure instead returns `uncertain` and seals the gateway.

## Verification and tooling image

Follow [local setup](setup.md) to build `scripts/tool-image` and record its immutable
image ID. Provisioning resolves public packages; runtime checks remain offline.
The Dockerfile and wheel-lock helper are part of the shared project.

With both integration environment variables set:

```sh
python -m pytest tests/integration/test_runtime_integration.py -ra
```

Require zero skips. Missing tools are failed checks, not skipped successes. Keep
the image identity and actual command outputs with your evaluation results.
