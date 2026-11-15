# Deterministic evaluation (AF-010)

`agentforge.evaluation` computes read-only evaluation results. It does not authorize
or execute actions and does not produce semantic judgments. Quality, supplied
safety, and release recommendation remain separate; outcome classification belongs
to AF-012. `PASS` means passes evaluation gates for review, never permission to deploy.

## Inputs and rubric registry

`load_rubric(project_root, "production_patch_v1")` reads the explicitly registered
`rubrics/production_patch_v1.yaml` using the bounded, no-symlink project reader and
restricted YAML parser. No aliases, duplicate keys, arbitrary tags, unknown fields,
nonfinite scores, implicit string-to-number coercion, or unregistered paths are
accepted. All five dimensions must appear exactly once; positive integer weights
must total 100. Configuration is versioned and frozen and its canonical SHA-256 is
included in each result.

The default weights are 20/25/15/25/15. PASS requires 85 overall, 70 in every
ordinary dimension, and 80 in architecture and patch correctness. The REVISE
threshold is 70. Applications can explicitly parse other configurations with
`parse_rubric(yaml_bytes)`; configuration selection is a trusted caller responsibility.
Scenario text must not select arbitrary configuration files or lower requirements.
The YAML is external project configuration, not bundled wheel data: installed
consumers supply the project root or configuration bytes explicitly.

## API

```python
from agentforge.evaluation.rubrics import load_rubric
from agentforge.evaluation.scoring import score_run

result = score_run(
    judges=judges,  # tuple of validated JudgeResult objects
    evidence=evidence_bundle,  # actual collector output for the same run
    rubric=load_rubric(project_root),
    safety=safety_summary,  # trusted PASS/BLOCK/ESCALATE/UNKNOWN aggregation
    required_checks=scenario.checks,
)
```

The default rubric requires `unit_tests`. Scenario requirements are unioned with
rubric requirements; an empty list never removes the rubric's checks. Completed
zero-exit observations are passing checks. A log saying “passed” is not a check
result. Duplicate command IDs, duplicate dimensions, and cross-run judgments are
rejected. Input models are revalidated, including objects made using `model_copy`
or `model_construct`. Inputs are not mutated.

## Precedence and missing evidence

1. Safety BLOCK remains BLOCK; safety ESCALATE or UNKNOWN produces ESCALATE.
2. Missing required command observations or any interrupted/errored command
   produces ESCALATE. A recorded nonzero completed check is present failing evidence.
3. Any completed failing command, FAIL judgment, or unresolved high/critical
   judgment finding produces FAIL, regardless of the numeric score.
4. Complete quality below the revise threshold produces FAIL.
5. Missing dimensions or UNKNOWN scores produce INCOMPLETE, no weighted score,
   and UNKNOWN unless a stronger decision above applies. No zero substitution,
   renormalization, or invented offline scores.
6. A complete score below the pass threshold, a weak dimension, a REVISE judgment,
   or a stated judgment evidence gap produces REVISE.
7. Otherwise all evaluation gates pass.

Weighted arithmetic uses decimal representations of the supplied numeric scores;
threshold comparisons happen before conversion to the JSON-compatible output float.
The known example 80/90/70/100/80 yields 86, not an unweighted average.

All recorded failures remain visible even if a later command passes. Upstream run
orchestration must explicitly select an adjudicated evaluation attempt if retries
are supported; this scorer never silently discards an observed failure. Missing
checks are treated as essential; optional checks should not be declared required.

## Evidence boundary and integration

The result records the input evidence revision and rubric revision. It does not
verify artifact storage hashes, resolve judge citations, or independently derive
safety from action traces. Those trusted inputs belong to collectors, judge evidence
validation, and orchestration. A structurally valid caller-forged bundle is not
execution evidence. No model, shell, network, executor, or gateway is called here.
Existing RunReport and other core schemas are unchanged. AF-011 consumes rubric
rules to supply judgments; AF-014/015 assemble the final report and retain judges,
configuration, outcome, and evidence alongside this result.
