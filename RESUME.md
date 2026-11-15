# AgentForge worker resume

Read AGENTS.md, AGENTFORGE_PROJECT_PLAN.md, STATUS.json and current ticket handoff.
Execute one ticket at a time in dependency order; preserve approvals and actual evidence.

## Current checkpoint

- **2026-11-15: private publication authorized** to `nishantsingh93/agentforg`
  (exact spelling). Local `git init -b main` succeeded. GitHub repository creation
  failed (CLI API connection error); token lookup exits 1 with no token available.
  Browser access host unavailable. No publication or hosted CI result. Restore
  CLI access, then continue approved publication; do not request authorization again.
  This supersedes historical destination and Git initialization blockers below.

- **AF-017 CI/license patch approved and applied locally (2026-11-13).**
  User approved exact prepared scope. `.github/workflows/ci.yml` and two pyproject
  license keys applied; 665 tests with no skips, typing/lint/format/build pass.
  Evidence: `AF-017-approved-checks.json`, `AF-017-approved-review.json`.
  Do not ask for patch approval again. GitHub account supplied: nishantsingh93;
  repository name/creation visibility still pending user answer. `gh repo list`
  cannot reach GitHub API from session. No publication or hosted CI yet.
  AF-017 stays incomplete until actual hosted CI succeeds. Older approval blockers
  below are historical.

- **AF-017 partially complete; protected approval and hosted CI pending.**
  Found existing docs/license/security/tutorial and CI proposal not tracked in STATUS.
  Restored `docs/tickets/AF-017.md`; fresh 665 tests pass / 16 Docker skips; typing,
  lint, format and pip check pass. Rechecked current package/source/manifest/license
  hashes against clean-install/build evidence. No protected edits applied.
  Exact proposal: `docs/proposals/AF-017-ci.patch`; scope/risk:
  `docs/approvals/AF-017-ci.md`. Requires explicit scoped approval before application.
  No Git metadata or remote; need intended GitHub repository and any publication
  authorization, then actual passing hosted CI. Do not declare all tickets complete.
  Earlier “AF-017 not started” notes below are stale.

- **AF-016 verified.** Fresh operator wheel/sdist match all 53 Python sources;
  temporary installation and installed benchmark CLI run/score pass on 50 cases.
  Source/test/corpus hashes unchanged from the 25-ticket-test / 663-suite-test
  verification. See `docs/verification/AF-016-final-review.json` and
  `AF-016-package-review.json`. Earlier build blockers below are historical.
  Labels remain provisional; no expert review or online model results claimed.
  Next **AF-017**, pending and not started; workflow changes need scoped approval.


- **AF-016 implemented; package verification blocked.** See `docs/tickets/AF-016.md`
  and `docs/judge-calibration.md`. 50 synthetic cases with provisional labels,
  blinded inputs, expert-review protocol, provider prediction API and offline CLI,
  metrics with counts/intervals/kappa/citations/usage and disagreements. Final checks:
  25 ticket tests (including real CLI integration) pass with zero skips; full suite
  663 passed / 16 existing Docker skips; typing, lint, formatting, pip check pass.
  Build fails: setuptools absent locally and PyPI DNS unavailable. Run
  `.venv/bin/python -m build` in normal Terminal and review new package artifacts
  before closing. Old AF-015 archives are not AF-016 evidence. No protected changes,
  no online model calls, no invented expert review. Next AF-017 remains pending.
  Evidence: `docs/verification/AF-016-final-checks.json`, `AF-016-cli.json`,
  `AF-016-build.json`, `AF-016-review.json` and `AF-016-integration.xml`.


- **AF-015 verified.** Operator evidence `AF-015-real-20261113T034846487561Z`
  has one real reporting integration pass, zero skips/errors/failures, exit 0.
  Fresh wheel/sdist match all 47 source files; temporary wheel install and installed
  report/compare CLI/import checks passed. See `docs/verification/AF-015-final-review.json`
  and `AF-015-package-review.json`. Original build exit code unavailable; validated
  artifacts establish packaging evidence. No source/protected changes at closure.
  Next: **AF-016**, not started. Earlier AF-015 blockers below are historical.


- **AF-015 implementation complete; verification blocked (2026-11-12 local).**
  Reviewed existing reporting implementation; added `scripts/verify_af015.py` and
  restored `docs/tickets/AF-015.md`. 638 tests passed / 16 Docker skips; full typing,
  lint and formatting passed. Explicit integration fails at approved Docker socket
  permission boundary; package build lacks setuptools. Run verifier and build in
  normal Terminal, then review fresh evidence. AF-014 remains verified; older
  statements that AF-015 is unstarted or AF-014 lacks build verification are stale.
  No protected changes. Next ticket AF-016 only after AF-015 verification.


- **AF-014 verified (2026-11-12).** Final review:
  `docs/verification/AF-014-final-review.json`. Latest real CLI run:
  `AF-014-real-20261112T193219183792Z`, three expected tests passed, zero skips,
  exit 0. Operator produced new wheel/sdist; independently checked all 43 Python
  sources against both archives, installed wheel into a temporary target and
  verified installed CLI/imports. Package evidence: `AF-014-package-review.json`.
  Original build command exit code was not supplied; artifact and install checks
  are observed evidence. 619 local tests, typing/lint/format checks retained.
  Next: **AF-015**, pending and not started. Older blockers below are historical.

- **AF-014 real Docker acceptance verified (2026-11-12 19:31 UTC).**
  Reviewed `AF-014-real-20261112T193127819418Z/`: three expected CLI tests passed,
  zero skips, exit 0. Hashes: `docs/verification/AF-014-integration-review.json`.
  Only package build remains unverified; dist files still predate this ticket.
  Run `.venv/bin/python -m build` in normal Terminal, then inspect success and
  new artifacts before closing AF-014. Earlier Docker blockers below are historical.


- **AF-014 implemented; acceptance verification blocked (2026-11-12).**
  See `docs/tickets/AF-014.md` and `docs/runs.md`. CLI offline smoke F01/F04,
  run coordinator and 17 new unit regressions are implemented. Full suite:
  619 passed / 15 explicit Docker skips; mypy, Ruff lint/format, pip check pass.
  Actual verifier attempted three cases and failed Docker preflight: approved
  local socket absent. Existing approved Colima restart was denied writing its
  configuration by session filesystem permissions. Do not bypass this boundary.
  Build also failed: setuptools/cache absent; PyPI DNS unavailable. Old dist
  files are not evidence. Run the three operator commands in the ticket handoff,
  inspect fresh evidence, then close AF-014. No new approval needed for existing
  setup scope. AF-015 remains pending; do not mark the dependency verified.
  Evidence: `docs/verification/AF-014-checks.json`, `AF-014-build.json`, and
  `AF-014-real-20261112T192513305423Z/`. Earlier checkpoints below are historical.

- **AF-013 verified.** Operator evidence from 2026-11-11 19:26 UTC confirms
  all four expected real Docker cases passed, zero skips/failures/errors, exit 0.
  Reviewed result.json, pytest.log and integration.xml; hashes recorded in
  docs/verification/AF-013-final-review.json. Prior 602 passing local tests and
  typing/lint/format/build evidence retained. No source changes during closure.
  Next: **AF-014**, run orchestration and CLI; pending, not started.
  Earlier checkpoints below are historical.

- **AF-012 implementation and acceptance tests verified.** See docs/tickets/AF-012.md.
  Read-only outcome oracles, all five categories, explicit expected Good Triage,
  and ambiguity handling implemented. 37 ticket tests; full suite 568 passed,
  8 local Docker skips; mypy/Ruff/offline build pass. Separately recorded AF-009
  integration is now verified (8 passed, zero skips). Next: AF-013 seeded scenarios.

**AF-009 dependency verified.** Final evidence:
`docs/verification/AF-009-final-review.json`. Older checkpoint entries below are
historical; the final AF-009 verification supersedes their integration blockers.

- **AF-011 verified.** Five read-only criterion judges, provider interface and offline
  UNKNOWN implemented. 47 focused tests; full suite 509 passed/4 Docker skips.
  Typing/lint/build and AF-011 formatting pass; full formatting fails only on
  separately owned tests/unit/test_runtime.py. See docs/tickets/AF-011.md.
  AF-012 awaits verified AF-009; preserve AF-008/009 owners' status and evidence.

- **AF-010 verified on 2026-11-10.** Existing implementation reviewed; 50 focused
  tests pass, full suite 402 passed/4 Docker skips, mypy/lint/build pass. Fixed
  scoring example whitespace; full formatting now passes. See
  docs/tickets/AF-010.md and docs/verification/AF-010-recheck.json.
  AF-011 is eligible (AF-005/010 verified); AF-008 operator check remains pending.

- **AF-001–007 verified.** Do not restart completed tickets.
- AF-005 operator run: docs/verification/AF-005-real-20261110T065758677966Z/.
  Inspected result.json, log and XML: exit 0, 3 passed, zero skipped. This closes the
  earlier missing Docker verification. The older AF-005-real.log/XML are skipped
  historical results, not the latest evidence. No more AF-005 rerun is needed.
- AF-006: pure adapter contracts, deterministic correct/flawed owned F01 demo,
  trusted bounded submission driver, proposal-only traces; no executor capabilities
  passed to adapters. Handoff docs/tickets/AF-006.md; checks 212 passed at that stage.
- AF-007: approved pure risk classifier/context/policy, exact scopes, fail-closed
  missing evidence, protected-path approval and critical blocks. 90 policy tests.
  Handoff docs/tickets/AF-007.md; docs/policy.md explains trusted context limits.
- **AF-008 implementation complete; real integration unverified.** User explicitly
  approved docs/approvals/AF-008-gateway.md. Do not request approval again.
  Gateway, grant registry, fixture executor, typed receipt integration and tests
  implemented. See docs/tickets/AF-008.md and docs/gateway.md.
- Latest suite: **402 passed, 4 skipped**. Includes 50 separately present scoring
  tests not implemented/claimed by this worker; leave that work intact. AF-010's
  tracker status has not been changed here. Typing (43 source/test files, 45 with
  verifier scripts), lint, AF-008 scoped formatting and sdist/wheel build pass.
  Full formatting check fails only on existing docs/scoring.md example whitespace;
  it was not modified because it belongs to separate work. Exact evidence:
  docs/verification/AF-008-checks.json and AF-008-extra-checks.json.
- Attempted `.venv/bin/python scripts/verify_af008.py` in this session: exit 1,
  Docker preflight failures. Diagnostic confirmed **permission denied** on approved
  local socket; no fixture execution. Saved run:
  docs/verification/AF-008-real-20261110T172426876950Z/. This is failed evidence,
  not the required operator verification. Do not bypass permissions.
- Next: user runs `.venv/bin/python scripts/verify_af008.py` in normal Terminal.
  Require `VERIFIED: 4 passed, zero skipped`; inspect new result/log/XML before
  closing AF-008. No new approval is needed for that command. The helper uses the
  saved approved local daemon and pinned image. AF-005 helper selects its original
  three tests; AF-008 helper selects all four. No install/download/permissions change.
- AF-009 depends on AF-008 and has not started. AF-009 and AF-011–017 remain pending; AF-010 was separately reverified.

## Approvals and boundaries

AF-001–005 scoped approvals and local Docker setup approval persist. AF-007 policy
proposal explicitly approved by user “approve”; do not ask again within that scope.
AF-008 was explicitly approved separately; its implementation stays within that
scope. Future policy/deployment/CI changes still require their own scoped approval.
No dependencies, schemas, CI, authentication, sandbox permissions or deployment
settings changed in AF-006/007. No production credentials or integrations.

Supported installed Python adapters are trusted code; pure contracts are not OS
confinement. Agent/model/scenario text remains untrusted data. AF-008 supplies execution wiring and receipt validation for the AF-006 protocol. Policy decisions
are not execution evidence; its IDs are not complete payload commitments.

## Environment

Workspace /Users/nishantsingh/Documents/code/agentforge. Use .venv/bin/python
(Python 3.14.8). No Git repo: previous git init denied .git writes; do not bypass.
No subagents requested or used. Session Docker socket access is restricted;
operator Terminal verified containment with the approved dedicated local daemon.
Saved daemon/image settings: runs/local-sandbox-setup/20261109T174139780721Z/settings.json.
Do not replace sandbox execution with host execution or pull arbitrary images.

Checks: `.venv/bin/python -m pytest -ra`, `.venv/bin/python -m mypy`,
`.venv/bin/python -m ruff check .`, `.venv/bin/python -m ruff format --check .`.
Build: `PIP_NO_INDEX=1 PIP_FIND_LINKS=/private/tmp/agentforge-wheels .venv/bin/python -m build`.
Temporary wheel cache is not durable. Update status and handoff after each ticket.


## AF-009 update — approved implementation, integration unverified

User approved docs/approvals/AF-009-runtime.md before protected dispatch edits.
Runtime checks and single-use synthetic canary/rollback simulation are implemented.
Full pytest: 516 passed, 8 skipped; full/scoped mypy, lint, formatting and isolated
package build pass. Evidence: docs/verification/AF-009-checks.json.
Explicit `.venv/bin/python scripts/verify_af009.py`: exit 1, eight Docker preflight
failures, no fixture execution. Saved under
`docs/verification/AF-009-real-20261110T194912141474Z/`.
Operator command requires access to the existing approved daemon and an approved
pinned image already containing ruff/mypy/build/build prerequisites. No tool/image
installation, infrastructure or permission change was performed or authorized.
Read docs/tickets/AF-009.md and docs/runtime.md before resuming. Require eight real
tests passing without skips before marking AF-009 verified. AF-011 has a separate
verified tracker entry. Next AF-009-dependent ticket is AF-012 after closing this
integration gap. Do not replace real integration with fake-Docker unit evidence.

## Operator evidence update — 2026-11-10 19:53 UTC

Reviewed `docs/verification/AF-009-real-20261110T195309295443Z/` result, log and
JUnit XML. Combined command exited 1: **5 passed, 3 failed, zero skipped**.
All four AF-008 cases passed, closing its integration gap; AF-008 is now verified.
AF-009 unit_tests passed. Its lint/typecheck/build cases failed because the approved
container image lacks ruff/mypy/build. AF-009 remains integration-unverified.
Earlier preflight-failure notes above are historical; this operator run reached
Docker and executed fixtures. Review summary: docs/verification/AF-009-operator-review.json.
Next step: scoped approval for docs/approvals/AF-009-tool-image.md, then provision a
pinned local tool image and require all eight real tests passing. No image or runner
changes have been applied for that proposal. Do not rerun with the unchanged base
image expecting those missing tools to appear.

## Approved tool-image implementation update

The user approved docs/approvals/AF-009-tool-image.md. Added
scripts/tool-image/Dockerfile, scripts/tool-image/lock_wheels.py and
scripts/provision_af009.py; extended verify_af009.py with --settings and runner
validation with exact local sha256 image-ID support. Repository-digest support,
mutable-tag rejection, container isolation, quotas and cleanup are preserved.
Tests cover local ID mismatch, exact ID, invalid IDs and hash-lock construction.
No project dependency manifest or policy/grant changes.

Local verification: 528 passed, 8 skipped; extended mypy, lint, formatting and
isolated package build pass. Full command/output/exit evidence is stored in
`docs/verification/AF-009-tool-image-checks.json`. Initial lint import warning was
fixed without assertion changes. No Git repository is available for branch/diff.
Reviewed edits for immutable identity checks, minimal build context, no credential
inheritance, and preserved sandbox restrictions.

Attempted `.venv/bin/python scripts/provision_af009.py`: exit 1 at Docker info,
permission denied on the approved socket. No image was built, no tools installed,
and no new lock/settings generated. Exact failure evidence:
`runs/tool-image/20261111T002128053747Z/commands.json`.
AF-009 remains implementation-complete / integration-unverified. AF-008 remains
verified by the prior operator run. No additional approval needed within this scope.

Next operator step in normal Terminal:
`.venv/bin/python scripts/provision_af009.py --verify`
This saves new settings separately and automatically runs all eight real tests.
Inspect the resulting evidence before closing AF-009 or proceeding to AF-012.

## Resume verification — 2026-11-11 04:37 UTC

AF-009 remains implementation complete / integration unverified. No source or
protected-area changes were needed. Read the project plan, AGENTS.md, status and
resume records, AF-009 handoff/runtime docs/approval records, provisioning and
verification scripts, and runtime test inventory. Existing ownership separates
runtime evidence from policy authorization and uses disposable synthetic state.
Plan: rerun approved provisioning and local checks; preserve failed evidence and
close only after eight real integration passes. Risk: treating skipped tests or
provisioning success as runtime verification; neither is accepted.

Commands and results (also in docs/verification/AF-009-resume-checks.json):
- `.venv/bin/python -m pytest -ra`: exit 0, 528 passed, 8 Docker skips because
  explicit integration settings were absent.
- `.venv/bin/python -m mypy`: exit 0, 57 source files.
- `.venv/bin/python -m ruff check .`: exit 0.
- `.venv/bin/python -m ruff format --check .`: exit 0, 103 files.
- `PIP_NO_INDEX=1 PIP_FIND_LINKS=/private/tmp/agentforge-wheels .venv/bin/python -m build`:
  exit 0 in disposable source copy; exact executable/cwd/output recorded in
  docs/verification/AF-009-resume-build.json; sdist and wheel built.
- `.venv/bin/python scripts/provision_af009.py --verify`: exit 1, permission denied
  at Docker info, before image construction or fixture execution. Exact command
  and output: runs/tool-image/20261111T043723549567Z/commands.json.

Only tracker/handoff and verification artifacts changed. No tests weakened,
policy bypass, dependency edits, or permissions changes. No Git repository exists,
so a feature branch/Git diff remains unavailable. Existing scoped approval persists;
no additional approval requested. Session socket access prevents final verification.
Run `.venv/bin/python scripts/provision_af009.py --verify` in normal Terminal;
require eight passes and zero skips, then inspect saved result/log/XML before
marking verified. Next dependent ticket: AF-012; not started here.

## Provisioning bug fix — vendored wheel metadata

Operator evidence `runs/tool-image/20261111T043824268282Z/commands.json` shows
Docker info passed and downloads succeeded; lock construction failed with
`ValueError: ambiguous wheel metadata`. Inspected Dockerfile, lock generator,
provisioning tests and cached setuptools 80.10.2 wheel: nested vendored dist-info
entries were incorrectly counted as wheel identities.

Plan/patch: select only root-level dist-info/METADATA in
`scripts/tool-image/lock_wheels.py`; add tests in `tests/unit/test_tool_image.py`
for vendored metadata, absent root metadata, and multiple root metadata entries.
Approved provisioning scope covers this repair. Hashes still cover entire wheel
bytes, and ambiguous root identities remain rejected. No pins, policy, dependency
manifest, Dockerfile or sandbox permissions changed. Reviewed patch: additive
assertions, no test weakening, no runtime authorization changes.

Verification: `.venv/bin/python -m pytest -ra` exit 0 (531 passed, 8 Docker skips);
`.venv/bin/python -m mypy`, `.venv/bin/python -m ruff check .`, and
`.venv/bin/python -m ruff format --check .` each exit 0.
`.venv/bin/python -m mypy scripts/tool-image/lock_wheels.py tests/unit/test_tool_image.py`
exit 0. Actual cached setuptools 80.10.2 wheel now produces its exact version and
SHA-256 lock entry. Evidence: docs/verification/AF-009-vendored-metadata-checks.json.
Package build not repeated: this patch changes only provisioning script/tests;
previous successful build is AF-009-resume-build.json. Real image build/integration
remain unverified due to session socket restriction; operator should rerun
`.venv/bin/python scripts/provision_af009.py --verify`. Require eight passes and
zero skips before closure. Next dependent ticket remains AF-012.

## Final verification — 2026-11-11 04:40 UTC

**AF-009 verified.** This supersedes historical integration-blocked notes above.
Reviewed operator result.json, pytest.log and integration.xml under
`docs/verification/AF-009-real-20261111T044000128589Z/`: exact eight expected
cases passed, zero skips/failures/errors, command exit 0. Command:
`.venv/bin/python -m pytest tests/integration/test_sandbox_integration.py tests/integration/test_runtime_integration.py -ra --junitxml=docs/verification/AF-009-real-20261111T044000128589Z/integration.xml`
(exact absolute argv retained in result.json).

Approved provisioning completed with all recorded command exits 0. Settings,
image-id.txt and image inspection agree on immutable image
`sha256:214264c2d50efe80f7e1efacc905cc1bbd5a36912fbd775b8f62840388c295de`.
Tool hashes and settings retained under `runs/tool-image/20261111T043952065408Z/`.
Review and artifact SHA-256 references: docs/verification/AF-009-final-review.json.
Prior 531-test local suite, static checks and package-build evidence remains valid;
no source changed during this closure. The eight formerly skipped integrations are
now separately verified. Healthy canary progression, degraded-canary verified
rollback, failed-rollback escalation and missing-health blocking are covered by
the existing passing runtime unit tests.

Changed only STATUS.json, RESUME.md, this handoff and the final review artifact.
No additional approvals required; no policy, permissions, dependency or deployment
edits. Review confirmed retained failure history and evidence-backed completion.
Synthetic telemetry remains synthetic; no claim of real production readiness.
Next dependency-ordered ticket: AF-012 (AF-009 and AF-010 verified), not started.

## AF-015 — 2026-11-12

Reporting implementation present; see `docs/tickets/AF-015.md` and
`docs/reporting.md`. Read-only JSON/HTML and baseline CLI preserve UNKNOWNs,
validate evidence and retain metric counts/coverage. No protected areas changed.
AF-014's newer operator evidence at `AF-014-real-20261112T193127819418Z` confirms
three real tests passed; its earlier tracker/handoff still contain stale Docker
failure notes. Its package-build gap was not claimed resolved.
AF-015 local reporting tests/static checks pass, but new real integration fails
Docker preflight and build lacks setuptools/network access. Retry the exact commands
in reporting docs in the approved environment, inspect outputs, then close AF-015.
Next ticket is AF-016 after verification; it was not started.
