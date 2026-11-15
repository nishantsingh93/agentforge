# AF-010 — Rubric registry and deterministic scoring

Assigned explicitly for parallel work while another worker owns AF-008. Dependencies
AF-002 and AF-005 are verified. AF-009 work was canceled before changes. No agents
were spawned. Shared contracts, gateway files, STATUS.json and RESUME.md remain
owned by existing work; this ticket's authoritative progress is its own handoff.

Read: AGENTS.md; AGENTFORGE_PROJECT_PLAN.md (especially rubric, precedence, contracts,
and AF-010); core/schemas.py, scenario.py, fixtures.py, trace.py, evidence.py;
tests/unit/test_schemas.py; README.md; pyproject.toml; saved AF-005/007 handoffs.
Patterns: frozen strict versioned contracts, bounded YAML and explicit file registry,
separate observed ToolResult and model claims, independent quality/safety/outcome.

Objective: produce deterministic quality and release recommendations from supplied
judgments and actual collected checks without invoking or authorizing actions.

Owned additions: evaluation/{__init__,rubrics,scoring}.py;
rubrics/production_patch_v1.yaml; tests/unit/test_scoring.py; docs/scoring.md;
AF-010 plan/handoff/verification files; scripts/verify_af010_build.py.
No shared schema, dependency, policy enforcement, sandbox, auth or CI changes.

Tests: numeric example; exact thresholds and critical minima; incomplete/offline
judgments; safety over 100 quality; observed contract/integrity failure over PASS;
timeouts/missing checks; configurable weights/thresholds; duplicate/cross-run inputs;
unsafe YAML; registry constraints; deterministic and immutable inputs. Full tests,
typing, lint/format and isolated package build with captured commands and exit codes.

Risks: treating scores or logged claims as evidence, renormalizing missing scores,
threshold float drift, weak custom configuration and silently discarding failed
attempts. Mitigations: no execution API, explicit evidence requirements, decimal
comparisons, validated versioned configuration, conservative failure retention.
Authenticity of collector input and safety aggregation remain trusted caller duties;
citation validation is AF-011, orchestration AF-014. No runtime safety policy edits.
