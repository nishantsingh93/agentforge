# AgentForge

Break your agents before production does.

AgentForge is a local-first lab for evaluating AI engineering agents on owned,
synthetic failure scenarios. It reports **quality, deterministic safety and outcome
separately**. It does not authorize production deployment.

AF-001–AF-016 are verified. AF-017 documentation, licensing and security review are
implemented locally; its [approved CI workflow](docs/approvals/AF-017-ci.md) is applied
but still needs a successful hosted GitHub Actions run. See [STATUS.json](STATUS.json) for evidence and remaining gates.

## Install from source

Obtain the maintainer-provided full source repository/archive. No public remote is
configured in this workspace; [contributing](docs/contributing.md) explains checkout
and prerequisites. From the source root on macOS/Linux with Python 3.12+:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m agentforge --help
python -m agentforge scenarios list
```

Initial installation requires public packages or a prepared cache. Keep the source
fixtures, registries and rubrics; they are not embedded wheel data. No model
credentials are needed for the offline features.

## Try the offline benchmark without Docker

```sh
mkdir -p runs/benchmark
python -m agentforge benchmark run --offline --split all > runs/benchmark/predictions.jsonl
python -m agentforge benchmark score runs/benchmark/predictions.jsonl --split all > runs/benchmark/report.json
```

The 50 reference cases have **provisional synthetic labels**, not expert ground
truth. Offline scores/confidence stay UNKNOWN. Report generation succeeds without
claiming model quality or release readiness. See [metrics and review protocol](docs/judge-calibration.md).

## Evaluate a disposable fixture

Follow [setup](docs/setup.md) to select a reviewed local Docker socket and immutable
tooling image, then:

```sh
python -m agentforge run --suite smoke --offline
```

Correct F01/F04 smoke exits **4**, because semantic judgments are unavailable.
Known failures exit 1; unavailable Docker exits 3 with no host fallback. The summary
prints the suite ID for [JSON/HTML reports and comparisons](docs/reporting.md).
See [run semantics and limitations](docs/runs.md). No doctor, network model transport,
production deployment or arbitrary host-shell command is exposed by the CLI.

## Contribute and inspect the boundaries

- [Contributor setup, checks and review cycle](docs/contributing.md)
- [Tested adapter tutorial](docs/adapter-tutorial.md)
- [Scenario registry](docs/scenarios.md) and [failure lab](docs/failure-lab.md)
- [Threat model and security review](docs/security.md), [reporting security issues](SECURITY.md)
- [Authoritative project plan](AGENTFORGE_PROJECT_PLAN.md) and [agent instructions](AGENTS.md)

The original project code is licensed under [Apache-2.0](LICENSE). Dependencies
retain their own licenses. Read the security model before running untrusted input;
installed Python plugins and the Docker/host runtime remain trusted components.
