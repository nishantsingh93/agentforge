# Security model

Review scope: local v0.1 source, documented boundaries and existing regression
coverage. This is a maintainer-oriented code/design review, **not an independent
penetration test or certification**. No real production integration is present.
Synthetic seeded successes do not prove universal containment or safe deployment.

## Assets and trust boundaries

Protect host files/credentials, policy decisions, approval scope, fixture isolation,
evidence integrity and truthful reports. Treat agent instructions, source/README,
fixtures, stack traces, logs, tool output and model responses as untrusted data.
Trust the operator-selected project root, installed application/adapter/provider
code, reviewer-maintained policy/fixture registry, local Docker daemon and image,
and host/kernel runtime. Untrusted fixture Python executes only in the disposable
container; installed Python plugins execute as trusted host code.

| Boundary / threat | Implemented control and evidence | Residual limitation |
| --- | --- | --- |
| Scenario traversal, YAML injection, mutable fixtures | Strict bounded loader, registered paths, no aliases/merges, canonical regular files and pinned snapshots; `test_scenario.py`, `test_fixtures.py`, `test_seeds.py` | Operator-chosen roots and reviewed registry contents remain trusted; legitimate repinning requires review |
| Unknown actions or forged authority | Typed allowlist, deterministic default deny/escalate, exact scope and preconditions; `test_policy.py` | Policy context must be supplied by trusted wiring, never model text |
| Dispatch before authorization, stale grants | Gateway audits/checks before dispatch, refreshes context, consumes scoped expiring grants, seals on uncertainty; `test_gateway.py`, `test_approvals.py` | Single-writer in-process authority, not distributed authorization; synthetic grants are not production credentials |
| Fixture host/network access and resource exhaustion | No host mounts/socket, nonroot, read-only root, no network, dropped caps, quotas, bounded transport and verified cleanup; `test_sandbox.py`, real sandbox integration | Kernel/daemon/image compromise and container escape remain possible; Docker is not a universal security boundary |
| False tool success, stale checks and unsafe rollback | Actual tool IDs/exits, final-state checks, independent oracles and simulator observations; runtime/runner/oracle tests | Synthetic telemetry is not real operational evidence; malicious Docker can lie |
| Fabricated judge evidence or policy override | Strict read-only requests, citation checks, offline UNKNOWN, deterministic score precedence; judge/scoring tests | Citation existence is not semantic entailment; trusted provider code can still perform arbitrary host actions |
| Artifact tampering and HTML injection | Content-addressed files, hash chains, identity checks, bounded no-follow reads; escaped HTML/CSP; evidence/trace/reporting tests | Hashes are consistency checks, not signatures; wholesale replacement is outside this integrity model |
| Credential leakage | Collector redacts known credential forms and configured literals before persistence; redaction tests | Arbitrary secrets/encodings may be missed; raw trusted in-memory receipts exist. Never ingest production credentials |
| Benchmark overclaiming and contamination | Provisional labels, blinded requests, preserved denominators, uncertainty, review provenance; benchmark tests | Public holdout is not secret; expert review remains outstanding; reported usage is transport-supplied |
| CI supply chain / untrusted PR code | Hosted-runner workflow with read-only token, credential-free checkout, full SHA actions, no privileged PR trigger, bounded artifacts | Passing CI must be verified for the revision being evaluated; package indexes and runner image remain trust dependencies |

The controls above were traced to source in core fixture/artifact/trace/redaction,
guardrails policy/gateway, sandbox runner, judges, scoring and report loading/rendering.
Tests establish specific observed behaviors, not universal safety. Skipped tests do
not establish containment. Inspect the [workflow results](https://github.com/nishantsingh93/agentforg/actions)
for the revision you use. Dependency consistency (`pip check`) is distinct from a
vulnerability audit; neither replaces source review.

## Operational and publication rules

Use only owned synthetic fixtures in an isolated local Docker environment. Never
use a production daemon, host secret mount, real auth token, customer data, remote
production endpoint, privileged container or host fallback. Provision dependencies
before evaluation; the fixture runtime remains network-disabled. Retain generated
container identity when cleanup is uncertain; stop and escalate rather than claim
recovery or globally delete resources.

Do not publish raw receipts, local environment/config, `runs/`, cached credentials,
or arbitrary logs. Review sanitized artifacts before sharing. CI should upload
only explicitly selected test/report/build artifacts with short retention, never
entire working directories or hidden files. No model secrets or deployment keys are
needed for offline PR checks. Do not run untrusted PR jobs on self-hosted runners.

Full action SHAs and minimal permissions follow
[GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).
Dependency auditing uses [pip-audit](https://github.com/pypa/pip-audit)
command without automatic fixes; findings require reviewed dependency changes.

## Current limitations

Before claiming release readiness, review passing CI for the exact revision,
benchmark label provenance, supported-platform results, artifact handling and the
limitations above. Reference labels remain provisional; the CLI ships F01/F04
demos and offline judges. Production actions are simulated only. A completed
benchmark is not certification or permission to deploy.
