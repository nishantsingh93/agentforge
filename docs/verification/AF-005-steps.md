# Verify AF-005 with the previously approved local Docker setup

Recommended: run this single command in macOS Terminal. It loads the previously
approved settings automatically and fails verification if any test skips:

```sh
cd /Users/nishantsingh/Documents/code/agentforge
.venv/bin/python scripts/verify_af005.py
```

Require `VERIFIED: 3 passed, zero skipped`. Evidence is saved under a unique
`docs/verification/AF-005-real-<timestamp>/` directory. Reply “done”; the agent can
inspect it. The wrapper does not mark tickets verified automatically.

Alternative manual steps (paste the entire block in the same Terminal session):

```sh
cd /Users/nishantsingh/Documents/code/agentforge
export AGENTFORGE_TEST_DOCKER_HOST='unix:///Users/nishantsingh/.colima-agentforge/agentforge/docker.sock'
export AGENTFORGE_TEST_IMAGE='python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df'
.venv/bin/python -m pytest tests/integration/test_sandbox_integration.py -ra --junitxml=docs/verification/AF-005-real.xml > docs/verification/AF-005-real.log 2>&1
printf 'pytest exit: %s\n' "$?"
cat docs/verification/AF-005-real.log
```

Require exit 0, **3 passed**, **zero skipped**. The intentional failing command
inside the third test is expected evidence; the outer integration test must pass.
The first two checks repeat AF-004 isolation/timeout/cleanup; the third verifies
actual sandbox output redaction, failure preservation and trace replay.

Settings are copied from the successful prior run's settings.json, not a new image
selection. This does not install tools, download images, change permissions, or use
production credentials. If daemon preflight fails, retain the log and inspect the
local setup before retrying; never replace Docker with host fixture execution.

Reply “done” after running; the agent can read both files from this workspace,
check the counts and update STATUS.json. A skipped run does not close AF-005.
AF-006 implementation follows this gate; its prepared plan is docs/tickets/AF-006-plan.md.

## Verifier checks

- `.venv/bin/python -m mypy src tests scripts/verify_af005.py`: exit 0, 25 files.
- `.venv/bin/python -m ruff check scripts/verify_af005.py`: exit 0.
- `.venv/bin/python -m ruff format --check scripts/verify_af005.py`: exit 0.
- Direct helper checks: valid three-case report accepted; skipped, failed, errored,
  empty and malformed reports rejected; exit 0. No Docker invocation in these checks.
- Initial script-only mypy invocation exited 1 because the editable package was
  treated as an untyped dependency; checking src and tests alongside it resolves
  module discovery without suppressions or changing dependencies.

Reviewed existing AF-005-real.log/XML: three tests skipped for absent settings;
not verification evidence. The new wrapper's full Docker execution remains pending.
