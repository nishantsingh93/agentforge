# AF-008 — Proposed action gateway and synthetic approvals

Scoped approval granted by the user’s “approve” response. Implementation applied; local checks pass, real integration remains pending. AGENTS.md protects policy
and secrets-handling changes; project plan section 13 requires scoped review.
AF-006 and AF-007 are implemented and verified dependencies.

## Exact proposed changes

New guardrails/gateway.py, approvals.py and executor.py; tests/unit/test_gateway.py,
test_approvals.py and an owned sandbox/check integration test. Extend the adapter
submission integration only as necessary to consume a typed gateway receipt;
retain separate decision and observed-result events. Update docs and handoffs.
No dependency, CI, container security profile or production integration changes.

1. Gateway is the sole supported adapter execution interface. Revalidate request,
   obtain fresh trusted context from injected provider, and evaluate AF-007 policy
   immediately before dispatch. Record request and policy event before a side
   effect; failure to record means no execution. BLOCK/ESCALATE never invoke executor.
2. REQUIRE_APPROVAL can proceed only through a trusted synthetic approval registry.
   Bind each grant to run ID, full canonical request payload (excluding the token
   reference), exact action type/target, policy version and expiry. Trusted issuer
   creates opaque synthetic references; agents cannot mint grants. Store grants
   only in memory; collector redacts references. No real user secrets, credentials,
   external approvals, browser or account access.
3. Validate expiry with an injected clock, exact request binding, run/scope/version,
   and single-use consumption. Wrong/missing/stale/already-used approval refuses
   dispatch. Approval cannot override a BLOCK, missing evidence, or unsupported
   executor operation. Recheck policy against fresh context at dispatch; preserve
   the original REQUIRE_APPROVAL event plus explicit approval-validation audit.
4. Bind idempotency keys to canonical request content and run. Exact repeats return
   a recorded prior receipt without executing twice; changed payload with the same
   key is rejected. In-flight/uncertain execution cannot be blindly retried. This
   v0.1 gateway is single-process/single-writer; durable distributed exactly-once
   guarantees are out of scope and must not be claimed.
5. Executor supports only read_file/edit_file over owned in-memory FixtureSnapshot
   copies and run_check through the existing Docker SandboxRunner. Edits construct
   a new bounded snapshot/digest; no host source edits, arbitrary shell commands,
   directory traversal or direct production execution. dry_run validates/records
   but performs no mutation/command. Only actual run_check results become ToolResult.
6. deploy_service/delete_data/edit_authentication do not gain execution support
   here. Unsupported dispatch is rejected even with approval; AF-009 owns future
   disposable rollout simulation. No permissive fallback.
7. Return typed receipts with policy decision, explicit execution state, and actual
   observations/references. Timeouts/errors/cleanup failures stay failures or
   uncertain outcomes. Never synthesize command success, claim success from ALLOW,
   or conceal failed audit persistence after execution. Failures seal the operation
   against automatic retries and retain available sanitized evidence.

## Tests and risk

Spy assertions: every BLOCK/ESCALATE/missing approval/invalid grant/unsupported
operation/dry-run/audit-write failure causes zero executor calls. Validate correct
synthetic grant, stale expiry, wrong run/scope/payload/version, reuse, idempotency
conflict and repeat, changing context between request and dispatch, partial failure,
timeout, adapter trace provenance and immutable snapshot copies. Real Docker check
uses owned fixtures and existing approved daemon/image only; record skips honestly.
Run full pytest, typing, lint/format and build.

Risk: this is the first dispatch boundary; a mistaken grant check or stale context
could authorize a side effect. Mitigate with exact bindings, non-overridable policy
blocks, fail-closed audit/evidence checks, injected spies and isolated execution.
Python interfaces do not confine malicious installed Python; arbitrary plugins are
outside the trusted adapter model. No production safety claims.

Approval scope: implement the listed AF-008 files, integration and tests only.
Rollback: stop using gateway and remove new modules; keep existing trace evidence.
No data migration, host deletion, sandbox relaxation or production access.
