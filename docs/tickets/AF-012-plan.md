# AF-012 read and plan

Goal: deterministic scenario expectations and all five outcome categories, explicit
expected refusal/triage, and human adjudication for ambiguous labels.

Read: AGENTS.md, AGENTFORGE_PROJECT_PLAN.md, STATUS.json, RESUME.md;
core schemas/evidence/trace/artifact and judge context interfaces;
evaluation rubric/scoring modules and scoring tests; runtime checks/rollout and
runtime tests; gateway audit emission and gateway tests; scenario YAML/docs,
AF-009/010 handoffs, pyproject.toml and the AF-010 build helper.

Patterns: strict frozen versioned contracts; evidence stored as content-addressed
files and hash-chained events; pure evaluation separate from action authorization;
trusted harness configuration; simulator recovery validated against state/health.
AF-010 is verified. AF-009 implementation exists but real Docker tool-image checks
remain unverified; this ticket consumes its pure simulator and leaves that gap open.

Plan announced before edits: add evaluation/oracles.py and evaluation/outcome.py,
collector-backed unit/integration regression coverage in tests/unit/test_outcome.py,
and taxonomy/API/handoff documentation. Preserve the existing OutcomeResult schema.
Track missing or conflicting labels separately with a nullable outcome wrapper.
Use data-only reviewed profiles rather than scenario-defined executable callbacks.
Update only AF-012 tracker state after verification.

Regression risks: fabricated success, missing evidence counted as failure/success,
blocked protected actions automatically treated as failure, overlapping labels
silently resolved by highest score, retries hiding failure, forbidden behavior
hidden by passing tests, rollout success claims contradicting state, cross-run or
tampered citations, permissive/unknown predicate configuration.

Checks: focused and full pytest, mypy, Ruff lint/format, offline isolated package
build. Review added files and tracker diff; Git branch/diff unavailable because this
workspace has no .git metadata. No protected modifications, new dependencies,
production operations, policy override, executor path or approval changes planned.
