# AF-011 plan

Read AGENTS.md, project specification, core schemas/trace/artifacts/evidence,
rubrics/scoring, collector and scoring tests, AF-005/010 handoffs and pyproject.toml.
Dependencies AF-005/010 verified. Existing patterns: frozen strict contracts,
canonical hashes, replayable trace, independent deterministic score/safety gates.

Own new judges/{base,context,prompts}.py and providers/{base,offline}.py packages,
unit tests and judge documentation. Shared schemas, policy, execution, dependencies
and CI remain unchanged. No protected-area approval needed for this design.

Provide five versioned criterion prompts through one provider-neutral evaluator.
Verify collector bundle/trace/file hashes, supply immutable serialized data without
action tools, validate strict JSON and all citations/identity, record usage/time and
configuration hashes. Offline returns UNKNOWN with no score/confidence. Errors
remain explicit and never silently become model judgments.

Tests: all five criterion fixtures, missing evidence/offline, forged references and
ranges, mismatched identity, malformed JSON, input immutability, untrusted instructions,
collector integration and existing scorer BLOCK/observed failure precedence.
Run full pytest, mypy, Ruff lint/format and local offline package build.

Risks: citation existence is not semantic truth; trusted Python providers are not OS
confined; hashes need trusted collector provenance; provider version pin is supplied
by caller. No SDK, credentials, live model service or production integration needed.
