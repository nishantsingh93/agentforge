# Security model and AF-017 review

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
| CI supply chain / untrusted PR code | Proposed hosted-runner workflow with read-only token, credential-free checkout, full SHA actions, no privileged PR trigger, bounded artifacts | Workflow applied locally but not hosted-tested; package indexes and runner image remain trust dependencies |

The controls above were traced to source in core fixture/artifact/trace/redaction,
guardrails policy/gateway, sandbox runner, judges, scoring and report loading/rendering.
Relevant tests were inspected and the local suite is rerun for AF-017. Prior real
Docker checks have ticket-specific evidence; skipped local tests are never counted
as new containment proof. Exact AF-017 commands/results are in its ticket handoff.

## Review findings and disposition

| ID | Finding | Disposition |
| --- | --- | --- |
| R01 | Older docs claim gateway/runtime/sandbox are future or unverified despite later evidence | Correct current docs; keep old ticket/provisioning logs as historical evidence |
| R02 | No license, contributor setup or runnable adapter tutorial | Add Apache-2.0 text and tested example; metadata change proposed for review |
| R03 | No installed workflow or Git repository/remote | Prepare exact workflow diff; require approval and actual hosted results before CI acceptance |
| R04 | Python 3.12 minimum advertised, local tests mainly Python 3.14/macOS | Proposed Ubuntu matrix tests both 3.12 and 3.14; compatibility remains hosted-unverified |
| R05 | Dependency ranges and image/tool downloads depend on public upstream supply | Preserve approved manifest; propose pinned audit tool, record resolutions/artifacts, fail audit on findings; no silent pin updates |
| R06 | Global project goals exceed current CLI/demo and calibration evidence | Document F01/F04 CLI limit, absent doctor/online transport and provisional labels; do not declare all v0.1 release gates passed |

No enforcement or permission change was needed for these documentation findings.
The review does not claim that no vulnerabilities exist. No vulnerability audit
result is inferred from `pip check`: that command only checks dependency consistency.
The proposed dependency audit requires advisory-service access and an actual run.

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
Dependency auditing uses the proposed [pip-audit](https://github.com/pypa/pip-audit)
command without automatic fixes; findings require reviewed dependency changes.

## Release evidence still needed

AF-017 cannot close until actual hosted CI passes. Its scoped workflow and license
metadata patch are approved and applied locally. Before claiming the broader v0.1 release, separately review human benchmark
labels, the complete five-step product demonstration, supported-platform evidence,
public repository settings, artifact handling and the limitations above. Ticket
completion is not a certification or permission to deploy.
