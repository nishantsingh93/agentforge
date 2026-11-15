# Version-one contract decisions (AF-002 verified)

All top-level payloads require `schema_version: "1"`. Unknown versions fail rather
than silently migrate. Future versions need explicit migration code and tests.
The plan's scenario `version` is independent: it identifies scenario revisions.

Wire format is JSON. Use `model_validate_json` for untrusted serialized inputs.
For already parsed YAML, AF-003 must preserve JSON semantics while rejecting
unsupported YAML types, duplicate keys, unsafe tags and aliases as appropriate.
Strict Python validation deliberately does not coerce lists into tuple fields.

The eight models are `Scenario`, `ActionRequest`, `PolicyDecision`, `TraceEvent`,
`EvidenceBundle`, `JudgeResult`, `OutcomeResult`, and `RunReport`. All forbid extra
fields and non-finite numbers. Nested contract fields are frozen; embedded JSON
maps remain mutable. Persisted evidence must be serialized and hashed by AF-005.

Action arguments are a closed typed record checked against the action type.
The allowlist describes the v0.1 demo's file, check, and synthetic operation
requests. A recognized action does not mean permission to execute it. AF-007/008
must independently classify and authorize every request. `approval_token` is a
synthetic reference identifier, never a production credential.

File references use canonical relative POSIX paths, SHA256 digests and ordered
positive line ranges. Event references include immutable revisions. Syntax alone
does not establish provenance; later evidence/judge modules must resolve citations
against actual stored contents. Path validation does not replace symlink-aware
filesystem containment in the fixture loader and sandbox.

Judge UNKNOWN requires a null score, null confidence, and a reason in
`missing_evidence`. Known judgments require citations. The report requires exactly
the five rubric dimensions and consistent run IDs. Quality is incomplete if any
score is unknown; no aggregate is allowed in that case. Release PASS cannot be
represented alongside incomplete quality or nonpassing safety. Numerical scoring,
thresholds, decision precedence and observed check interpretation belong to AF-010.

Outcome categories map to 0–4 independently of quality and safety. An outcome may
be absent while evidence is insufficient; it must not be invented to fill a report.
Count-based metrics retain numerator and denominator, including zero trials.

JSON Schema export is pure (`export_json_schemas`) or stdout-only via
`python -m agentforge.core.schemas`. No files, commands, provider calls, policy
decisions or state mutations are triggered by validation.
