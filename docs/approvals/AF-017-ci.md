# AF-017 — Workflow and license-metadata proposal

Status: **approved by user and applied locally on 2026-11-13**.
User explicitly approved application and supplied the nishantsingh93 GitHub account.
Repository creation/visibility/destination remain separately unconfirmed.
Exact reviewable diff: [AF-017-ci.patch](../proposals/AF-017-ci.patch).
The exact proposed workflow and two pyproject license fields are now applied.
Validation: `docs/verification/AF-017-approved-checks.json` and
`docs/verification/AF-017-approved-review.json`. Hosted CI has not run.

## Requested scope

1. Add `.github/workflows/ci.yml` exactly as proposed: push, pull_request and manual
   dispatch; `contents: read`; credential-free checkout; Ubuntu hosted runners;
   timeouts and concurrency cancellation; no deployment, publishing, secrets,
   privileged PR trigger, self-hosted runner or automatic dependency fixes.
2. Check Python 3.12 and 3.14, full unit tests plus real offline benchmark CLI,
   typing/lint/format/dependency consistency, wheel/sdist build and selected JSON
   artifacts. Require no test skips in those jobs.
3. Build the existing reviewed tooling Dockerfile on the disposable hosted runner,
   pin its resulting immutable image ID, run every integration without skips,
   then actual F01/F04 offline CLI smoke and HTML/JSON reports. Explicitly require
   exit 4 plus Bullseye/INCOMPLETE/UNKNOWN; never reinterpret exit 4 as release PASS.
   This extends image provisioning to hosted CI, not the local production host.
4. Run pinned `pip-audit==2.10.1` in a separate disposable job. Audit installed
   dependencies, skip only the editable unpublished project itself, fail on
   collection errors/findings, upload JSON. Never run `--fix` or ignore advisories.
5. Upload only explicitly listed test/report/build artifacts for seven days,
   including after failure; exclude hidden files and whole working/run directories.
6. Add only `license = "Apache-2.0"` and `license-files = ["LICENSE"]` under
   `[project]` in pyproject.toml. Existing dependencies and version ranges stay intact.
   This publishes the license already supplied by the project's Apache-2.0 target.

## Evidence and risk

Action tags were resolved from official GitHub API refs and pinned to full commit
SHAs; exact responses are in `AF-017-upstream-references.json`. The Apache license
was fetched from the official URL and hashed. Current source tests/build and clean
source-install evidence are recorded in the AF-017 handoff. YAML/shell/embedded-Python
proposal checks are static validation, not proof of GitHub Actions execution.

CI executes untrusted PR code on disposable hosted runners. Its token is read-only
and checkout credentials are not persisted; no application/model/deployment secrets
are referenced. The runner, Docker service, pinned base, GitHub actions and public
package/advisory services remain supply-chain trust dependencies. Project dependencies
use their existing reviewed ranges; this proposal does not claim a fully locked build.
Package installation and image provisioning need network; fixture containers remain
under the unchanged no-network/nonroot/no-host-mount runtime restrictions.

An unavailable image architecture, audit finding or upstream outage must fail the
job and be investigated. Do not relax pins, grant permissions, suppress a failure
or change dependency ranges without a new scoped review. Artifacts contain only
owned synthetic evaluation material but still warrant review before publication.

No hosted CI can be claimed until the approved workflow is committed to a real
GitHub repository and successful run evidence is inspected. This local workspace
has no Git metadata/remote. Repository creation, publication, branch protection and
private-reporting settings are separate actions, not authorized by this patch.

## Rollback and approval

Rollback removes the new workflow and the two license metadata keys; it does not
prune Docker resources or erase previous verification evidence. The license and
unprotected contributor/security documentation remain.

Approve this exact patch and hosted disposable CI provisioning/audit scope before
application. [AGENTS.md](../../AGENTS.md) says: “Do not modify CI/workflows,
dependency manifests/lockfiles ... without explicit human review and scoped approval.”
The [project plan §13](../../AGENTFORGE_PROJECT_PLAN.md) likewise requires an exact
proposal and approval before applying protected changes. The AF-017 assignment
explicitly retains this requirement; it is not a waiver.
