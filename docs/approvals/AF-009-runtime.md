# AF-009 — Runtime verification and synthetic rollout simulator

Status: scoped approval granted by the user’s “approve” response. Implementation
applied within the scope below; see docs/tickets/AF-009.md for verification gaps.

## Read and dependency findings

Read AGENTS.md, AGENTFORGE_PROJECT_PLAN.md, STATUS.json, RESUME.md,
docs/tickets/AF-008.md, docs/tickets/AF-010.md, docs/gateway.md,
docs/approvals/AF-008-gateway.md, pyproject.toml, fixtures/order-service/orders.py,
core/schemas.py, core/evidence.py, adapters/base.py, guardrails/{gateway,executor,
policy,taxonomy}.py, sandbox/{runner,bootstrap}.py, tests/unit/test_gateway.py and
tests/integration/test_sandbox_integration.py.

Existing ownership: strict frozen contracts; policy owns authorization; gateway
owns pre-dispatch audit, exact synthetic grants and idempotency; executor owns
disposable snapshots; sandbox owns bounded Docker execution; collector owns
sanitized evidence. AF-010 scoring is already separately implemented.

AF-008 implementation exists, but its handoff and tracker still record real
integration as unverified. Its existing operator command is
`.venv/bin/python scripts/verify_af008.py`; require four passes, zero skips.
Do not describe that dependency as fully verified until successful evidence exists.
There is no Git repository, so branch/diff review is unavailable.

## Exact proposed scope

1. Add `src/agentforge/runtime/{__init__,checks,rollout}.py` and focused tests.
   Strict versioned runtime results retain command/event references and snapshot
   identities. Keep runtime status separate from quality score and outcome.
2. In `guardrails/gateway.py`, extend supported dispatch from unit tests to exactly
   `unit_tests`, `lint`, `typecheck`, `build`, and disposable `deploy_service`.
   Preserve all policy checks, grants, context refresh, refusal, dry-run, audit,
   replay and uncertainty sealing. Unsupported operations remain denied. Do not
   change `policy.py`, approval issuance, risk tiers, or protected-path rules.
3. In `guardrails/executor.py`, dispatch the four checks to the sandbox and
   delegate deployment only to an explicitly configured owned in-memory simulator.
   Reject deployment without that simulator or outside simulated-production.
   Add a typed rollout observation to the executor observation contract; gateway
   validates its consistency and records structured runtime evidence. An executed
   request means the simulator returned, not that rollout or recovery succeeded.
4. In `sandbox/runner.py` and `sandbox/bootstrap.py`, select commands by the typed
   check name only. Unit tests keep existing unittest discovery; lint uses
   `python -m ruff check .`; typecheck uses `python -m mypy --strict .`; build uses
   `python -m build --no-isolation .`. These run only in the disposable container,
   never a host shell. Trusted explicit tool configuration must ignore fixture
   lint/type configuration that could suppress checks or load plugins. Missing
   tools/build prerequisites, nonzero exits, timeout, and absent results remain
   nonpassing evidence; no installing, pulling images or network fallback.
   Keep current container identity, resource limits, network, mounts, permissions,
   cleanup and no-host-fallback behavior unchanged.
5. Runtime checker submits typed requests through Gateway and binds observations
   to the requested check and fixture snapshot. Only completed exit-zero commands
   with observed trace evidence pass. Missing, refused, uncertain, stale or
   mismatched evidence cannot satisfy a required check. Logs claiming success do
   not override actual status/exit codes. No fabricated model judgments.
6. A single approved deploy request covers a bounded synthetic lifecycle, including
   recovery; it is not an approval for later independent actions. Simulator input
   is trusted harness configuration, never executable scenario text. State is
   per-run, disposable, in memory, with no production/network/file mutation API.
   Compare baseline and canary error rate, p95 latency, availability and business
   success rate against explicit validated thresholds and observation windows.
   Record baseline -> canary -> expanded, or stopped -> rollback -> recovered /
   escalated. Missing baseline prevents canary. Missing/incomplete/stale canary
   evidence prevents expansion and attempts recovery. Recovery requires independent
   state equality to the baseline and healthy post-rollback observations.
7. Deterministic fault injection covers degraded canary, missing health evidence,
   rollback failure and claimed success with unchanged state. Keep claimed tool
   response separate from actual synthetic state. Failed or unverified rollback
   terminates in escalation, never recovery. Record before/after observations and
   terminal reasons through existing sanitized trace/evidence APIs.
8. Add `tests/unit/test_runtime.py`, additive gateway/sandbox coverage and owned
   integration fixtures. Update gateway/runtime docs and AF-009 handoff. A helper
   may verify the available approved Docker image, but cannot install tools or
   alter Docker settings. Preserve old assertions except the explicit supported
   operation expectations changed by AF-009; replace those with equivalent
   unsupported-operation cases and new approval/refusal coverage.

## Risks and validation

Expanding the dispatch allowlist is a protected authorization boundary change.
Incorrect status mapping could falsely report recovery or checks passing. An
unbound simulator could become an alternate execution path. Mitigations: existing
policy and exact approval binding before every dispatch, simulator available only
to trusted executor wiring, immutable typed evidence, terminal failure states,
and spy tests proving refusal never invokes execution.

Required cases: healthy expansion; all four metric failures; boundary thresholds;
invalid/nonfinite metrics; insufficient observation window; missing/stale baseline,
canary and rollback evidence; rollback restores actual baseline; rollback failure
and spoofed success escalate; no continuation after terminal state; isolated runs;
missing/wrong/expired approval; dry run and replay do not mutate; audit failure;
all four checks with success/nonzero/timeout/error/missing tool/mismatched evidence.

Run targeted tests, `.venv/bin/python -m pytest -ra`,
`.venv/bin/python -m mypy`, `.venv/bin/python -m ruff check .`,
`.venv/bin/python -m ruff format --check .`, and
`PIP_NO_INDEX=1 PIP_FIND_LINKS=/private/tmp/agentforge-wheels .venv/bin/python -m build`.
Record exact exit codes and Docker skips/failures. Real command checks require a
pre-provisioned approved image containing their tools; lacking it is an explicit
integration limitation, not permission to modify dependencies or infrastructure.

Approval requested: the AF-009 dispatch/executor/bootstrap extensions and runtime
modules/tests/docs listed above. No dependency manifests, lockfiles, CI, production
integration, authentication, secrets, sandbox permission or infrastructure changes.
Rollback: remove the new dispatch support and runtime modules; retain audit evidence.

Next dependency-ordered work after AF-009 verification: AF-011 (AF-005/010), then
AF-012 (AF-009/010), as appropriate to the existing completed tickets.
