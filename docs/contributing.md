# Contributing

Start with [AGENTS.md](../AGENTS.md) and the [project plan](../AGENTFORGE_PROJECT_PLAN.md).
One AF ticket at a time; retain actual command outputs and distinguish tested,
unverified and blocked work. Do not edit policy/gateway, authentication, secrets
handling, dependency manifests/locks, CI, deployment or sandbox permissions without
an explicit scoped review and approval. A ticket assignment alone is not that approval.

## Get a clean source checkout

This working copy has no Git metadata or published remote configured. Once the
maintainer supplies the repository URL, use:

```sh
git clone <maintainer-provided-repository-url> agentforge
cd agentforge
git switch -c af-NNN-description
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m agentforge --help
```

Replace the angle-bracket URL and ticket branch before running. Do not assume a
public repository exists. A source archive can also be unpacked into a new directory
and installed using the same commands. Keep the full source tree: fixture registries,
rubrics, benchmark data and examples are external inputs, not embedded wheel data.
Use Python 3.12+ on macOS or Linux; Windows sandbox support is not implemented.
Setup requires public package-index access or a prepared wheel cache. Evaluation
can then run without model credentials. No `agentforge doctor` command is implemented;
use help, registry validation and explicit sandbox preflight errors for diagnostics.

## Fast checks without Docker

```sh
python -m agentforge scenarios list
python -m agentforge validate --scenario scenarios/correctness/F01.yaml
python -m examples.inspection_adapter
python -m pytest tests/unit tests/integration/test_benchmark_integration.py -ra
python -m mypy
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m build
```

The adapter example prints a dry-run proposal only. It does not open fixture files
or authorize a read. Tests using a fake transport establish logic, not containment.
For JSON-only offline benchmark artifacts:

```sh
mkdir -p runs/benchmark
python -m agentforge benchmark run --offline --split all > runs/benchmark/predictions.jsonl
python -m agentforge benchmark score runs/benchmark/predictions.jsonl --split all > runs/benchmark/report.json
```

Read [calibration limits](judge-calibration.md). Labels remain provisional and
UNKNOWN remains unknown. Benchmark report generation exits 0, not a release approval.

## Real sandbox smoke

Follow [sandbox setup](setup.md), selecting a reviewed local Unix socket and pinned
image. Set both `AGENTFORGE_TEST_DOCKER_HOST` and `AGENTFORGE_TEST_IMAGE` before:

```sh
python -m pytest tests/integration -ra
```

Require zero skips for a real integration claim. Tests fail if explicit settings
are present but the daemon/image is unavailable. Never solve missing Docker with
host execution or relaxed sandbox flags. A successful offline evaluation CLI exits
4 because judges are UNKNOWN; the integration tests assert this expected outcome.
See [runs](runs.md) and [reports](reporting.md) for exit codes and artifact handling.

## Changes and review

Read affected interfaces, ownership, tests and policy first. State the cause/design,
smallest change, failure cases and risks before editing. Add regressions that catch
observable behavior, preserve existing assertions and validate strict output schemas.
Review diffs for dependency drift, unsafe authorization order, fabricated evidence,
secret leakage, stale checks and scope creep. Record exact test commands and exits,
including skips and environmental failures. Use the ticket handoff format in AGENTS.md.

New adapters follow the [tested tutorial](adapter-tutorial.md). Scenarios follow
[registry rules](scenarios.md) and [failure-lab oracles](failure-lab.md); fixtures are
untrusted inert data until executed inside the disposable sandbox. Do not import
fixture Python on the host. Updating hashes is deliberate review, not a way to
silence an integrity failure. LLM judges and synthetic approvals never grant real
production access.

## Publication and CI status

The [approved AF-017 workflow](approvals/AF-017-ci.md) is installed locally with
package license metadata. Hosted CI verification still needs a confirmed GitHub
repository and an actual passing workflow run.
Do not publish local `runs/`, virtualenvs, caches, credentials or raw operator logs.
Review artifacts before sharing; the redactor is not a universal secret detector.
The original code is offered under [Apache-2.0](../LICENSE); third-party packages
retain their own licenses. Package license metadata is applied and verified in the built wheel.
