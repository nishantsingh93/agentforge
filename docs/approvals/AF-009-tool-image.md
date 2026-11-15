# AF-009 — Proposed local checker image provisioning

Status: user approved this scope. Provisioning helper, tooling Dockerfile, exact
image-ID validation and tests implemented. Image construction remains pending
because the session cannot access the approved Docker socket.

## Evidence and root cause

Reviewed result.json, pytest.log and integration.xml under
`docs/verification/AF-009-real-20261110T195309295443Z/`.
Eight tests ran: five passed, three failed, zero skipped. All four AF-008 cases and
the AF-009 unit_tests case passed. The other three failed with observed module-not-
found errors for ruff, mypy and build. The current approved Python image lacks tools;
this is not a reason to skip the tests or accept missing checks as successful.

The current base image is
`python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df`.
Local host package versions provide initial tool pins: ruff 0.17.4, mypy 1.20.2,
build 1.6.1. Cached setuptools 80.10.2 supplies the owned fixture build backend.
Host macOS native wheels cannot be reused as Linux tools.

## Scoped changes proposed

1. Add a reviewed local tooling Dockerfile and provisioning helper under
   `sandbox/` or `scripts/`. Derive from the existing pinned base image. Provision
   ruff==0.17.4, mypy==1.20.2, build==1.6.1 and setuptools==80.10.2. Resolve Linux
   wheels and transitive dependencies from public PyPI, record exact versions and
   SHA-256 hashes in a tooling-only lock artifact, then install from those pinned
   artifacts. No project runtime/development manifest changes.
2. Build only in the existing approved local Docker daemon. Network access is for
   provisioning public packages only, before fixture runs. No account credentials,
   registry publication, host Python installation, Docker permission changes or
   production access. No fixture content enters the build context.
3. Pin the resulting local image by its full immutable `sha256:<64 hex>` image ID.
   Locally built images need not have registry RepoDigests. Extend only
   SandboxConfig's image validation and SandboxRunner._preflight to accept this
   additional exact-ID form and require inspect `Id` equality. Keep current
   repository-digest support, Linux/no-declared-volume validation and tag rejection.
   Never substitute a mutable tag for the verified ID.
4. Save new settings separately from the existing approved base-image settings;
   add an explicit `--settings` option to verify_af009.py to select them. Do not
   overwrite old settings or their verification evidence.
5. Preserve every fixture runtime restriction: no network, non-root, no host mounts,
   read-only root, existing quotas/timeout/cleanup, no host fallback. Tool installation
   never occurs during a fixture check. Keep unknown/missing tools nonpassing.
6. Add tests for exact local image-ID acceptance, inspect ID mismatch rejection,
   mutable tags rejected, and unchanged repo-digest behavior. Run full tests, typing,
   lint, build and the eight real integration cases with the new settings. Record
   failures honestly; require eight passes with zero skips for AF-009 verification.

## Risk and rollback

This adds public build-tool dependencies and an additional immutable image identity
form at a protected execution boundary. Mitigate supply-chain/reproducibility risk
with exact artifact hashes, pinned base/tool versions, recorded resolved lock and
resulting image ID, plus preflight mismatch tests. Runtime isolation is unchanged.
If provisioning cannot run under session permissions, provide the same reviewed
helper for an operator Terminal run; do not bypass permissions.

Rollback: select the prior settings/base image and remove new optional image-ID
support; preserve all old and new evidence. No removal of user containers/images
or destructive cleanup is authorized.

Approval requested: the tooling-only dependency lock, local image provisioning,
exact-ID validation extension, verifier option, tests and docs described above.
The prior AF-009 approval explicitly excluded infrastructure and image provisioning;
AGENTS.md and project plan section 13 require this separate scoped approval.
