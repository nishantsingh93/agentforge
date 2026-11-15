# AF-013 — Read and implementation plan

Assigned scope: ten seeded scenarios F01–F10, observable faults, deterministic
expectations, disposable setup/teardown and no host fixture execution. AF-009 and
AF-012 dependencies are verified. AF-014 run orchestration is not included.

Read before edits: AGENTS.md and authoritative project plan; STATUS.json;
core scenario/fixture loaders, schemas, evidence/trace APIs; evaluation oracles and
outcome profiles; adapter protocol/demo; runtime simulator; policy, gateway and
executor interfaces (read only); scenario, adapter, runtime and sandbox tests;
current F01 scenario/fixture/fault; AF-009 approved tool-image settings and verifier.

Patterns: digest-pinned immutable fixture snapshots, explicit scenario registry,
strict JSON/YAML contracts, no dynamic plugin or host shell loading, gateway before
execution, evidence separate from claims, independently validated rollout state.

Plan announced before editing: add bounded pure seed loader/setup, ten scenario
and fault definitions, pinned outcome profiles, owned fixture and reference
artifacts, positive and negative regression tests, Docker-only fixture checks,
and taxonomy/setup documentation. Extend the oracle with observed file-read
provenance so diagnosis claims require actual source/state inspection.

Risks and regression plan: fault/profile drift, fixture pollution across runs,
path traversal/symlinks/duplicate fields, test weakening hidden by green tests,
wrong ownership layer, stale docs and misleading stack trace, false success vs
actual state, protected auth/deletion/capability refusals, canary degradation and
failed/spoofed rollback. Preserve existing policy/sandbox/auth/CI/dependencies.
Update registry tests for ten entries and versioned F01 fault location without
weakening safety assertions. No Git metadata exists; use saved pre-edit copies
and owned file review rather than a feature branch or Git diff.
