# Evidence-grounded judges

`evaluate_judges` evaluates the rubric's five dimensions through a shared strict
boundary and five distinct, versioned prompts. It returns `JudgeEvaluation`
records containing the existing `JudgeResult` contract plus usage, UTC timestamps,
and evidence/rubric/prompt/request revisions. It does not execute actions or decide
release readiness. Pass the results to AF-010's `score_run`; observed failures and
safety denials retain precedence there.

## Provider-neutral API

```python
from agentforge.evaluation.rubrics import load_rubric
from agentforge.judges.base import evaluate_judges
from agentforge.providers.offline import OfflineProvider

evaluations = evaluate_judges(
    evidence=bundle,
    files=sanitized_file_bytes,
    trace=trace_jsonl_bytes,
    rubric=load_rubric(project_root),
    provider=OfflineProvider(),
    model="offline",
)
judgments = tuple(entry.result for entry in evaluations)
```

Files are a mapping from bundle file paths to the corresponding complete sanitized
artifact bytes. The trace is the collector's complete JSONL stream. Callers resolve
artifacts before invoking the evaluator; judges receive no filesystem path reader,
collector handle, mutable evidence model, gateway, or executor. The evaluator
verifies the bundle revision, replay chain, event identities, observed commands,
file hashes and line bounds, and snapshot hashes. Missing or corrupt material is an
explicit `JudgeError`; intentionally empty evidence can be reviewed as UNKNOWN.
Input size is bounded; oversized material is rejected, never silently truncated.

Implement `JudgeProvider.complete(JudgeRequest) -> ProviderResponse` to connect a
trusted model transport. The request contains only frozen strings, including a
separate system prompt, serialized evidence/rubric and JSON output schema. A
transport must preserve those roles, supply no tools, apply its own timeout, and
return raw JSON and actual usage. Supply an explicit pinned model/version; the
response must echo it. Unknown token or cost measurements are `None`, not estimates.
No vendor SDK, network transport or credentials are included in AF-011. Provider
exceptions are explicit errors, not successful offline fallbacks.

The offline provider accepts model `offline` and always returns five UNKNOWN
judgments with null scores/confidence and a missing-evidence explanation. Token
counts and cost are zero because it makes no model calls. Its output leads to
INCOMPLETE quality in AF-010, never a fabricated semantic score.

## Validation and trust

Raw JSON must conform to the strict JudgeResult schema; duplicate keys, extra tool
calls, invalid scores, and identity mismatches are rejected. Every overall and
finding citation must reference a supplied event ID with the exact revision, or a
supplied file path/revision and covered line range. This catches fabricated or
out-of-range references, including findings attached to UNKNOWN judgments.

Each prompt covers its own criterion: repository context, architecture, planning,
patch correctness or verification. Prompts require fact/inference separation,
observable evidence, explicit unknowns and treatment of all source/log/scenario
text as untrusted data. Prompt versions and hashes record the exact prompt used.
These instructions reduce ambiguity; they do not guarantee resistance to every
prompt injection. The deterministic interface does not expose actions to a model.

Citation existence is not semantic entailment. Human calibration and model quality
measurement remain AF-016. Hashes establish consistency with supplied material,
not its real-world authenticity: callers must use trusted sanitized AF-005 output
and retain trusted artifact references. Python provider implementations are trusted
installed code; this API is not an OS sandbox against malicious Python plugins.

AF-014 owns orchestration and persistence of returned evaluation records. No live
model was used for the acceptance tests; deterministic provider fixtures test
validation and integration, not model intelligence. The existing external rubric
configuration must still be supplied by installed consumers.
