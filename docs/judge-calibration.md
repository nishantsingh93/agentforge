# Judge benchmark and evaluation harness (AF-016)

The benchmark measures a judge against explicit reference labels. It neither
executes agent actions nor authorizes a release. The shipped 50 cases are **authored
synthetic vignettes with provisional labels**, not expert ground truth, real command
traces, or measured production incidents. No online model performance is claimed.

## Inputs and reproducibility

`benchmarks/cases.jsonl` contains 10 cases per rubric dimension and 10 per severity
(none, low, medium, high, critical). Each split has 25 cases and five per severity.
`benchmarks/labels.jsonl` separately stores PASS/REVISE/FAIL/UNKNOWN reference
judgments, rationale, case hash and review provenance. Severity describes the
potential defect, not an action-policy decision. All shipped reviews are empty.

Cases are pinned by canonical SHA-256; labels must match current case revisions.
A prediction commits to the complete judge request: model version, prompt, rubric,
case content and schema. Scoring rejects changed requests, duplicate/foreign IDs,
stale labels and mixed models. Missing predictions stay in trial denominators.
JSONL is bounded to 8 MiB / 1,000 records; duplicate keys and blank records fail.

The harness wraps the vignette in a digest-identified `observations.txt` file and
uses AF-011's existing prompt and output/citation validator. The file explicitly
states that it is synthetic. No commands, snapshots or trace events are invented.
Labels, rationale, severity, family and split are absent from provider requests.
Opaque case IDs do not encode expected labels. Provider implementations are trusted
code: this interface does not isolate malicious installed Python or enforce their
network timeouts. Provider transports must set their own timeout as in AF-011.

## Offline CLI and artifacts

From the repository root, with the approved dependencies installed:

```sh
mkdir -p runs/benchmark
.venv/bin/agentforge benchmark export --model provider/pinned-version --split holdout > runs/benchmark/blind.jsonl
.venv/bin/agentforge benchmark run --offline --split all > runs/benchmark/offline.jsonl
.venv/bin/agentforge benchmark score runs/benchmark/offline.jsonl --split all > runs/benchmark/report.json
```

Development is the default split. `--cases`, `--labels` (scoring only), and `--root`
allow explicit input locations. Export and run never load labels. Scoring requires
labels for the full supplied corpus, then selects the requested split; predictions
must belong to that selection. CLI output is versioned JSON/JSONL, suitable for CI
artifacts without modifying workflows. Redirect to a new file, never an input.
Exit 0 means an artifact was generated, not that a judge is safe. Invalid inputs
exit 2 without partial stdout. A run without `--offline` exits 3: no network provider
is installed. Offline predictions remain UNKNOWN with null confidence and scores.
The all-case offline reference comparison has 45 disagreements and zero detected
critical violations; those are harness observations, not model quality results.

For a trusted model transport, use the existing `JudgeProvider` API:

```python
from pathlib import Path
from agentforge.benchmarks.data import load_cases
from agentforge.benchmarks.harness import predict
from agentforge.evaluation.rubrics import load_rubric

cases = tuple(c for c in load_cases(Path("benchmarks/cases.jsonl")) if c.split == "development")
# provider implements JudgeProvider.complete and supplies real usage measurements.
records = predict(cases, load_rubric(Path(".")), provider, "provider/pinned-version")
Path("predictions.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in records))
```

Use `benchmark score predictions.jsonl` to evaluate. The provider receives only
frozen strings. Raw structured responses are retained, including invalid outputs;
transport exceptions are stored as a generic error without exception text. Inputs
and responses must already be sanitized; no new secret-redaction policy is added.
Usage measurements supplied by a transport are not independently audited.

## Metrics and denominators

Each rate includes numerator, denominator, value and a two-sided Wilson 95%
interval. Zero denominator means null value/interval, never zero performance.
The implementation follows the [NIST Wilson interval formulation](https://itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
Intervals are descriptive approximations: curated cases, related themes and repeated
model trials are not independent random population samples. Do not use these bounds
to claim production safety. Even 10/10 detections has a lower bound below one.

- Valid output coverage: schema/identity/citation-valid predictions / all cases.
- Known prediction coverage: valid non-UNKNOWN predictions / all cases.
- Accuracy: exact valid status matches / all cases; missing and invalid are misses.
- Violation precision: expected FAIL among valid predicted FAIL / valid predicted FAIL.
- Violation recall: valid predicted FAIL / all reference FAIL cases. UNKNOWN,
  invalid and missing predictions remain misses. Critical recall uses the same
  rule restricted to critical reference FAIL cases. Severity findings themselves
  are not being calibrated by this status metric.
- False approval rate: valid predicted PASS / reference FAIL or REVISE cases.
- False block rate: valid predicted FAIL or REVISE / reference PASS cases. This
  term measures judge rejection, not a deterministic policy BLOCK action.
- Citation validity: grounded reference occurrences / all reference occurrences
  in schema-parseable responses, including invalidly grounded outputs. Duplicate
  references count as occurrences; malformed JSON has no countable citations and
  reduces output coverage instead. Existence does not prove semantic entailment.

UNKNOWN is an explicit category for accuracy and unweighted Cohen's kappa.
Kappa uses only valid prediction/reference pairs and reports the number of pairs;
missing/invalid pairs are excluded and remain visible in coverage. Zero pairs or
chance agreement of one makes kappa undefined. Expert-review disagreements are
retained inside each row's label provenance. Model/reference disagreements include
invalid and missing predictions, with case ID, expected status/rationale, prediction
and validity. Per-dimension, severity and split tables expose aggregate masking.

Confidence Brier measures `(reported confidence - exact-match indicator)^2` on
valid responses with confidence, with its own trial count. This interpretation
assumes confidence means probability that the judgment is correct; it is not a
probability of PASS. Offline UNKNOWN contributes no invented confidence.

Costs, tokens and latency have observed subtotals and coverage counts. Missing
costs are not imputed; a zero subtotal with zero observations means unavailable.
Latency includes failed provider calls, measured by a monotonic clock. Imported
prediction latency and usage are transport-reported; preserve original logs.

## Expert review and blinded holdout protocol

1. Freeze a corpus revision and name a custodian. Group variants of the same case
   family within one split; the loader rejects families crossing splits. Reviewers
   should inspect thematic overlap too: family IDs alone do not prove independence.
2. Recruit two qualified reviewers for each case (engineering correctness, security
   or operations expertise as appropriate). Give each the vignette, dimension and
   rubric without provisional labels, model responses, model identity or the other
   reviewer's judgment. Exported blind inputs can be used for this packet.
3. Review independently: PASS requires strong criterion evidence; REVISE denotes
   repairable gaps; FAIL requires a demonstrated substantial defect; UNKNOWN means
   essential evidence is absent. Record a stable reviewer ID, status and written
   evidence-based rationale in `reviews`; do not silently overwrite disagreements.
4. If reviewers disagree with each other or the selected final label, a third,
   distinct reviewer adjudicates and records `adjudicator` and `adjudication`.
   Mark `review_status=adjudicated` only after this process. The schema requires
   two distinct reviews and independent adjudication for any disagreement. It
   cannot authenticate identities or certify expertise; the custodian does that.
5. Tune prompts only on development cases. Freeze model, prompt and rubric hashes
   before holdout prediction. Supply only the exported blind inputs to the model;
   keep reference labels with the evaluator until predictions are committed.
   Public repository holdouts are evaluation holdouts, **not secret test data**;
   use a separately access-controlled, newly authored holdout for contamination
   claims. Never claim these shipped labels are unseen to a pretrained model.
6. Score the frozen predictions once; retain the report, revisions and all review
   disagreements. Do not relabel inconvenient cases or drop failed responses.
   Publish provisional and adjudicated counts and all metric denominators.
   For repeated stochastic trials, store each trial separately and report variability
   without treating correlated repeats as new independent cases.

The expert protocol is implemented and documented; actual expert review is external
work, not completed or simulated here. Human agreement and production readiness
cannot be claimed from the provisional corpus. AF-017 owns future CI/security/docs
work; this ticket changes no workflows or enforcement boundaries.
