# Run orchestration (AF-014)

From the repository root, select the already approved local Docker daemon and
reviewed image explicitly (no image downloads, daemon setup, or host fallback):

```sh
export AGENTFORGE_DOCKER_HOST=unix:///Users/nishantsingh/.colima-agentforge/agentforge/docker.sock
export AGENTFORGE_IMAGE=sha256:214264c2d50efe80f7e1efacc905cc1bbd5a36912fbd775b8f62840388c295de
.venv/bin/agentforge run --suite smoke --offline
.venv/bin/agentforge run --scenario F04 --agent demo-patcher-flawed --offline
```

These values identify this workstation's approved setup; other installations must
supply their own reviewed local socket and pinned image. CLI options `--docker-host`
and `--image` override the environment. `--root` locates the registry and rubric;
`--runs-root` sets the output directory. Paths are relative to the current directory.

The smoke suite contains F01 and F04. Both use scripted demo proposals, not model
inference. The correct demo proposes the known repair; the flawed F01 demo fails
regression tests and the flawed F04 demo deliberately weakens fixture tests. The
independent integrity oracle must reject the latter even when its tests are green.
Default adapter construction remains proposal-only for existing API callers;
the CLI explicitly enables execution through the gateway.

## Outputs and exit codes

Each invocation allocates a unique `suite-<uuid>` and fresh `run-<uuid>` directories.
The suite's atomic `summary.json` identifies every attempted run and its exit code.
Each run retains `trace.jsonl`, content-addressed objects, `evidence.json` including
the patch diff and before/after snapshot identities, five `judge-*.json` records,
`outcome.json`, `score.json`, `report.json`, and `result.json`. Failures retain any
artifacts already collected and produce an error result; they never fabricate a
successful report. The raw scoring result is retained even when the independent
outcome forces a stricter final report decision. [HTML reports/comparisons](reporting.md) consume these artifacts without Docker.

| Code | Meaning |
| --- | --- |
| 0 | All evaluation gates pass (requires complete semantic evidence) |
| 1 | Observed failure, wrong outcome, unsafe refusal, or revision needed |
| 2 | Invalid selection/configuration |
| 3 | Docker/provider/infrastructure error or uncertain execution |
| 4 | Inconclusive because mandatory evidence is missing |

A correct offline smoke run exits **4**, not 0: the outcomes can be Bullseye while
all five semantic judgments remain UNKNOWN, quality INCOMPLETE, and release
UNKNOWN. Offline mode never invents scores. A known check/oracle failure exits 1
even offline. An expected protected-action refusal is safe only when the exact
refusal oracle passes and the independently classified outcome matches the profile.
It does not authorize that action or clear unrelated policy denials.

`--preflight-retries 0..2` retries only daemon/image checks before any fixture action.
Executed, refused, failed, timed-out, or uncertain actions are never automatically
retried. A fresh invocation starts new evidence; earlier attempts are not erased.
An infrastructure error stops the suite. Suite precedence is 3, then 1, then 4, then 0.

Repeatability means the same decisions, outcome categories, scores/unknowns and
pinned configuration for the same inputs. Run IDs, event IDs, timestamps, command
IDs, measured durations and evidence hashes intentionally vary.

## API and current limits

`agentforge.core.runner.run_suite` composes registered seeds, rubrics, a trusted
installed `AgentAdapter`, sandbox, provider, judges and oracles. Its provider and
model arguments allow installed provider integrations; the CLI currently has only
OfflineProvider and rejects online requests clearly before execution. Custom
adapters remain trusted installed Python; proposal-only contracts are not an OS
sandbox for malicious adapter implementations.

The shipped CLI demo supports F01/F04. Other registered scenarios can be supplied
to the Python API with a suitable adapter. The coordinator supplies no synthetic
approval tokens, service allowlist, or asserted rollout readiness; simulated
production requests fail closed. The simulator is attached for seeds that define
one, but this ticket does not introduce an approval UI or automatically grant
rollout permissions. Fixture commands always pass through Gateway and the existing
sandbox. Every required check must be supported; unknown checks fail validation.

## Real verification

The verifier uses the saved, approved tool-image settings without provisioning:

```sh
.venv/bin/python scripts/verify_af014.py
```

Require `VERIFIED: 3 passed, zero skipped`. It runs actual CLI smoke, repeated
smoke, and flawed-demo checks and saves command/log/XML evidence. Unit tests use
mock transport and are not proof of actual fixture behavior or containment.
