# Contributing to AgentForge

Contributions to scenario coverage, adapter examples, evidence validation and
reporting are welcome. Discuss significant changes in a repository issue before
implementation. Read the [security model](security.md) and the documentation for
the module you intend to change.

## Development setup

```sh
git clone https://github.com/nishantsingh93/agentforg.git
cd agentforg
git switch -c improve-scenario-coverage
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Use Python 3.12+ on macOS or Linux. Keep the full checkout: fixtures, registries,
rubrics and benchmark data are external inputs, not embedded wheel data. Access
is required while the repository remains private.

## Checks without Docker

```sh
python -m agentforge scenarios list
python -m agentforge validate --scenario scenarios/correctness/F01.yaml
python -m examples.inspection_adapter
python -m pytest tests/unit tests/integration/test_benchmark_integration.py -ra
python -m mypy src tests examples
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m build
```

The adapter example is proposal-only. Tests using a fake transport check logic,
not container isolation. For actual execution, follow [sandbox setup](setup.md),
set both `AGENTFORGE_TEST_DOCKER_HOST` and `AGENTFORGE_TEST_IMAGE`, then run:

```sh
python -m pytest tests/integration -ra
```

Report skipped tests and infrastructure failures honestly. A real integration
claim requires zero skips. The offline CLI intentionally exits 4 when mandatory
semantic evidence is unavailable; a report command exiting 0 means rendering
succeeded, not that the evaluated agent passed.

## Pull requests

Explain the problem, affected module and smallest intended change. Preserve
existing assertions and add regression coverage for changed behavior. Include
exact checks run and their results, including any checks you could not run.

Security-sensitive changes need explicit maintainer review: policy/gateway,
authentication, secrets handling, dependency manifests and locks, workflows,
deployment and sandbox boundaries. Never execute an action before authorization,
weaken containment to make a test pass, or replace missing evidence with a claim.

## Where to contribute

- [Adapters](adapter-tutorial.md): typed proposals, refusal handling and evidence receipts.
- [Scenarios](scenarios.md): pinned fixtures and independently testable expectations.
- [Failure lab](failure-lab.md): fault injection and outcome oracles.
- [Judges](judges.md): structured judgments with evidence citations.
- [Benchmark](judge-calibration.md): review provisional labels and measure disagreements.

Fixture files, scenario instructions, logs and model output are untrusted data.
Do not import fixture Python on the host. A changed fixture hash needs deliberate
review; updating a hash is not a substitute for investigating a failing check.

## Local files and shared evidence

Keep local run output, credentials, environments, development journals and machine
configuration out of commits. Share minimal sanitized reproductions and relevant
results in your pull request. Internal ticket records and operator transcripts are
not required to build, test or use AgentForge.

Original code is licensed under [Apache-2.0](../LICENSE). Dependencies retain their
own licenses. See [security reporting](../SECURITY.md) before disclosing a vulnerability.
