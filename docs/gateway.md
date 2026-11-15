# Action gateway (AF-008)

Gateway.submit accepts strict ActionRequest and returns Receipt. Trusted application
wiring owns the gateway, context provider, ApprovalRegistry, FixtureExecutor and
TraceCollector. Adapters receive text and return requests; no grant issuer or executor
capabilities are passed to them. Supported installed Python adapters remain trusted
code: a Python interface is not confinement for malicious imports.

## Authorization and audit

Each new request is revalidated, recorded, evaluated against current trusted context,
and audited before dispatch. Unsupported operations, BLOCK and ESCALATE never call
an executor. Context run/scenario identity must match the gateway. A second policy
check follows the initial audit; the whole trusted context must remain unchanged
after final authorization audit and immediately before execution. Context changes
cause refusal, even if the changed context might still allow a request. Missing or
invalid context/audit data stops and seals the gateway. No policy fallback is used.

For REQUIRE_APPROVAL, an explicitly supplied synthetic grant must match the full
canonical request excluding its token reference, run, exact scope and policy version.
The original policy requirement stays in the trace; a separate gateway ALLOW records
validated approval. Grant validation repeats after audit writes and consumes once
immediately before execution. A grant cannot override BLOCK, ESCALATE or unsupported
operations. Clock regression, nonfinite clock values, expiry and reuse are invalid.
Grant issue/validation APIs belong only to trusted wiring, not agent outputs.

Synthetic grant lifetime is at most one hour; registry and opaque references exist
only in memory. The collector redacts references. No real credentials or external
authority are involved. Issue a grant for the final request including its action ID,
idempotency key and dry_run value, then attach the returned approval_token. A denied
request is terminal for its key: a newly authorized attempt needs new action/key
identities and a correspondingly bound grant.

## Execution and receipts

Supported execution: read_file/edit_file over existing files in a validated in-memory
FixtureSnapshot, and run_check(unit_tests/lint/typecheck/build) via the Docker SandboxRunner.
Edits validate the complete candidate snapshot before replacing the in-memory value.
Host project files are never written. AF-009 adds deploy_service only for an explicitly
configured single-use in-memory simulator in simulated-production. Other check
names, delete_data and edit_authentication remain unsupported. No host execution
fallback. See [runtime verification](runtime.md) for health and recovery semantics.

Dry runs validate and audit but do not call the executor or consume a valid grant.
They do not prove that a runtime operation would succeed. Receipt states:
- refused: no dispatch, non-ALLOW decision, no execution observation.
- dry_run: authorized proposal only, no execution observation.
- executed: dispatcher returned a validated observation; commands require completed
  status and exit 0; rollouts require expanded status. This is not an independent
  semantic correctness verdict.
- failed: command failed/timed out/errored, or rollout blocked/recovered/escalated;
  observed results retained. Recovery is not successful task completion.
- uncertain: dispatch or subsequent audit failed; side effects may have occurred.

Only actual sandbox results become ToolResult events. File observations carry
source_snapshot_digest, the identity of raw in-memory fixture bytes, explicitly not
a persisted sanitized evidence revision. Read content and raw tool output can exist
in trusted in-memory receipts; never serialize receipts as public reports directly.
Use EvidenceCollector for sanitized persistence; its file/snapshot references hash
sanitized persisted bytes. Gateway audit notes contain metadata, not raw read content.

## Idempotency and failure limits

One single-writer Gateway per run. The run-local idempotency map binds each key to
the full canonical payload including token reference. Identical repeats return the
historical receipt with replayed=true, without dispatch or new authorization; changed
payload/key reuse and action-ID reuse with another key are rejected. Receipt event
references remain the original observations. Replaying an old ALLOW does not grant
permission to execute again.

Any uncertain operation seals the whole gateway; exact replay returns the recorded
uncertainty and never invokes the executor. Cancellation propagates, leaves the
operation incomplete and seals the gateway against retries. A post-execution audit
failure cannot turn into a success result, even if a ToolResult was obtained.
Registry and idempotency state are not durable across process restart; this is not
distributed exactly-once execution. Do not create a replacement gateway to retry an
uncertain run. Docker timeout/cleanup bounds remain those of the existing runner.

Adapter run_adapter now accepts decision-only test stubs or typed receipts. Receipt
references must match the same verified trace; refusal/failure/uncertainty stops the
plan. The driver's claim-linked proposal and gateway's authorization-bound proposal
are distinct trace events for the same action, not duplicate dispatches.

## Operator verification

Run in macOS Terminal with the existing approved Docker installation:

```sh
cd /Users/nishantsingh/Documents/code/agentforge
.venv/bin/python scripts/verify_af008.py
```

Require `VERIFIED: 4 passed, zero skipped`. The script uses the saved approved
socket/image, saves command/exit/log/XML under docs/verification/AF-008-real-<time>,
and rejects missing/skipped/failed cases. It does not install/pull/change permissions.
AF-005's older verifier now explicitly selects its original three checks so the new
AF-008 test does not change its expected test count.
