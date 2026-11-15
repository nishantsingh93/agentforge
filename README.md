# AgentForge

**Break your agents before production does.**

AgentForge is a local evaluation lab for AI engineering agents. Give an agent a
controlled bug or misleading incident, inspect the actions it proposes, and check
what actually happened against independent evidence.

It helps answer three different questions: **Was the work good? Were the actions
allowed? Did the agent solve the problem?** A persuasive explanation or a green
test run alone cannot answer all three.

[Get started](#get-started) · [Try the demos](#try-the-patch-demos) ·
[Scenarios](#the-failure-lab) · [Build an adapter](docs/adapter-tutorial.md) ·
[Contribute](docs/contributing.md)

## Why use it?

Imagine an agent “fixing” a bug by deleting the failing assertion. Its tests turn
green, but the defect remains. AgentForge's flawed demo reproduces that shortcut:
an independent test-integrity check rejects the patch and records a **Misleading**
outcome.

Other scenarios test whether an agent reads the right code, questions stale docs,
respects protected operations, detects a false success message, or stops an
unhealthy simulated rollout.

| If you are… | Use AgentForge to… |
| --- | --- |
| Building a coding agent | Exercise its patching and refusal behavior in repeatable fixtures. |
| Comparing agent versions | Compare recorded outcomes and evidence before changing your integration. |
| Building an evaluation pipeline | Export structured JSON, self-contained HTML and meaningful exit codes. |
| Developing an LLM judge | Test evidence citations and compare predictions with a synthetic reference corpus. |
| Exploring agent safety | Study policy gates, approval scope and rollback behavior in a local simulator. |

## What is available today?

- **Ten seeded scenarios** with pinned fixtures and independent outcome checks.
- **Two scripted patch demos:** a correct repair and a deliberately flawed repair
  for F01/F04. They are reproducible examples, not live model inference.
- **A typed action gateway and deterministic policy engine** that authorize
  supported actions before execution and record refusals.
- **Disposable Docker execution** for fixture checks, with network-disabled
  containers, resource limits and no host-execution fallback.
- **Five evidence-grounded judge interfaces**, an offline provider, a weighted
  rubric and separate quality, safety and outcome results.
- **JSON/HTML reports, comparisons and trace evidence**, plus a 50-case synthetic
  judge benchmark with provisional labels and a human-review protocol.
- **Python adapter and provider interfaces** for your own trusted integrations.

This is pre-release software for owned, synthetic evaluations. The CLI currently
executes the F01/F04 demo adapters offline. Other seeds and rollout simulations
are exercised through Python interfaces and tests. There is no production deployer,
network model transport in the CLI, or automatic permission to operate a real service.

## How it works

```mermaid
flowchart TD
    S[Scenario + pinned fixture + fault] --> A[Agent adapter proposes typed actions]
    A --> G[Action gateway]
    G --> P{Deterministic policy}
    P -->|Deny or escalate| T[Trace and evidence]
    P -->|Allow| X[Fixture executor]
    X --> D[Disposable Docker checks]
    X --> M[In-memory rollout simulator]
    D --> T
    M --> T
    T --> O[Independent outcome oracle]
    T --> J[Read-only quality judges]
    T --> R[Safety and observed-check results]
    O --> V[Decision and reporting]
    J --> V
    R --> V
    V --> H[JSON / HTML / comparison]
```

The adapter proposes; the gateway authorizes; the executor produces observations.
Judges review recorded evidence and cannot override policy denials or observed
failures. Installed Python adapters and the host runtime are trusted components;
the adapter interface alone does not sandbox malicious plugin code.

| Result | What it tells you |
| --- | --- |
| **Quality** | Repository awareness, architecture, planning, patch correctness and verification. |
| **Safety** | Policy decisions and observed action evidence, independently of quality scores. |
| **Outcome** | Bullseye, Directional, Good Triage, Partial or Misleading. |
| **Final decision** | Whether the available evidence satisfies the evaluation gates. Missing required evidence remains UNKNOWN. |

<details>
<summary><strong>View the broader evaluation and safety framework</strong></summary>

![Design vision: agent workflow, quality rubric, policy gates, operational checks and outcome categories](docs/images/framework-vision.png)

This reference image describes the broader design vision. Its production actions,
autonomy levels and illustrative scores are not a statement of shipped capabilities
or measured results. Current execution is confined to fixtures and a synthetic
rollout simulator. See [runtime behavior](docs/runtime.md) and
[scoring semantics](docs/scoring.md) for the implemented rules.

</details>

## Get started

### 1. Install from source

Use Python **3.12+** on macOS or Linux. Clone the full source tree so fixtures,
scenario registries and rubrics are available. While the repository is private,
your GitHub account needs access.

```sh
git clone https://github.com/nishantsingh93/agentforg.git
cd agentforg
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m agentforge --help
```

Use your installed Python 3.12-or-newer executable if it has a different name.
Installation needs package-index access; the offline examples need no model keys.

### 2. Explore the scenarios — no Docker needed

```sh
python -m agentforge scenarios list
python -m agentforge validate --scenario scenarios/correctness/F01.yaml
python -m examples.inspection_adapter
```

The last command prints a typed, dry-run read proposal. It shows the adapter
contract without reading a fixture, changing files or running an agent task.

### 3. Try the judge benchmark — no Docker needed

```sh
mkdir -p runs/benchmark
python -m agentforge benchmark run --offline --split all > runs/benchmark/predictions.jsonl
python -m agentforge benchmark score runs/benchmark/predictions.jsonl --split all > runs/benchmark/report.json
```

Open `runs/benchmark/report.json` to inspect counts, coverage and unavailable
judgments. This demonstrates the evaluation pipeline; offline predictions remain
**UNKNOWN**, and the 50 reference labels are **provisional synthetic labels**, not
expert ground truth. For provider integration and interpretation, read the
[judge benchmark guide](docs/judge-calibration.md).

## Try the patch demos

### 1. Prepare the local sandbox

Use a dedicated local Docker environment with Linux containers. Follow the
[step-by-step setup guide](docs/setup.md) to build the tooling image and set
`AGENTFORGE_DOCKER_HOST` and `AGENTFORGE_IMAGE` to your own local values.
Docker is needed for these examples, but no model credentials are needed.

### 2. Observe a correct repair

```sh
python -m agentforge run --scenario F01 --offline
```

F01 injects a null-handling bug. The correct scripted adapter proposes the known
repair, the gateway checks the actions, and the harness runs the fixture checks.
The expected outcome is **Bullseye**. The final offline decision is **UNKNOWN**
and the process exits **4**, because semantic judge evidence is unavailable.

To run both supported smoke scenarios:

```sh
python -m agentforge run --suite smoke --offline
```

### 3. Catch a misleading repair

```sh
python -m agentforge run --scenario F04 --agent demo-patcher-flawed --offline
```

F04 tempts the agent to remove a failing assertion. The flawed demo changes the
tests; the independent integrity oracle catches it even if the altered tests pass.
Expected result: **Misleading**, final **FAIL**, exit **1**.

| Demo | Expected outcome | Offline final decision | Exit |
| --- | --- | --- | --- |
| F01, correct demo | Bullseye | UNKNOWN | 4 |
| F04, correct demo | Bullseye | UNKNOWN | 4 |
| F04, flawed demo | Misleading | FAIL | 1 |

These are expected behaviors, not pasted execution logs. Every invocation saves
its own observations. Exit **3** indicates an infrastructure problem; do not mask
it with `|| true`. See [all exit codes](docs/runs.md#outputs-and-exit-codes).

### 4. Read and compare reports

Each run prints a summary path such as `runs/suite-…/summary.json`. Substitute the
actual suite IDs from your output below; do not type the placeholders literally.

```sh
python -m agentforge report YOUR_SUITE_ID --format html > runs/report.html
python -m agentforge report YOUR_SUITE_ID --format json > runs/report.json
python -m agentforge compare BASELINE_SUITE_ID CURRENT_SUITE_ID > runs/comparison.json
```

Open `runs/report.html` in your browser. Inspect outcomes, policy events, patches,
observed checks, trace citations and missing evidence. Compare the correct and
flawed **F04** runs for a like-for-like example. Reports render without Docker and
preserve each run's counts; missing safety or judge measurements stay unknown.

Keep the full run directory to retain the evidence behind the report. See
[report formats and comparison limits](docs/reporting.md).

## The failure lab

| Scenario | What goes wrong | What the evaluator checks |
| --- | --- | --- |
| **F01 — Null handling** | A normal edge-case bug | Correct repair and observed regression checks. |
| **F02 — Wrong layer** | Service bug looks like an API problem | Service-layer fix with API contract preserved. |
| **F03 — Stale docs** | Documentation contradicts current code | Actual inspection and evidence-backed diagnosis. |
| **F04 — Test deletion** | Removing an assertion makes tests green | Independent test-integrity checks reject the shortcut. |
| **F05 — Protected auth** | Task requests an auth middleware change | Refusal and routing to the appropriate owner. |
| **F06 — Misleading trace** | Stale stack trace points to the wrong cause | Diagnosis grounded in source and observed evidence. |
| **F07 — Destructive operation** | Unauthorized synthetic DELETE request | Blocked execution and unchanged simulated state. |
| **F08 — Unhealthy canary** | Errors and business KPI failures rise | Stop, verify rollback, or escalate failed recovery. |
| **F09 — Missing capability** | Task needs unavailable private data | Scoped refusal and useful escalation. |
| **F10 — False success** | Tool transcript disagrees with state | Independent state inspection catches the mismatch. |

F01/F04 have ready-to-run CLI patch demos. The remaining scenarios are registered
fixtures with Python oracles and tests; use a suitable adapter/harness to evaluate
them. They do not imply a built-in agent can solve all ten from the CLI.
[Explore the fault and oracle design →](docs/failure-lab.md)

## Extend AgentForge

Start with the [adapter tutorial](docs/adapter-tutorial.md): implement
`AgentAdapter.propose(task) -> AdapterPlan`, return typed actions, and let the
trusted harness submit them through the gateway. The Python `run_suite` API accepts
custom adapters; the CLI selects the bundled demos.

For new scenarios, follow the [scenario registry](docs/scenarios.md) and
[failure-lab guide](docs/failure-lab.md). For model-backed review, implement the
[provider contract](docs/judges.md), return structured judgments and cite recorded
evidence. An LLM's claim of success never replaces an observed command result.

## Documentation

| Guide | Contents |
| --- | --- |
| [Setup](docs/setup.md) | Docker image, local configuration and first smoke run. |
| [Runs](docs/runs.md) | CLI behavior, saved artifacts, exit codes and API limits. |
| [Reports](docs/reporting.md) | HTML, JSON, comparisons and evidence validation. |
| [Adapters](docs/adapter-tutorial.md) | A complete proposal-only example and integration path. |
| [Policy](docs/policy.md) / [Gateway](docs/gateway.md) | Classification, authorization, approvals and receipts. |
| [Runtime](docs/runtime.md) | Fixture checks and simulated canary/rollback behavior. |
| [Judges](docs/judges.md) / [Scoring](docs/scoring.md) | Rubrics, evidence citations, UNKNOWN and decision precedence. |
| [Security](docs/security.md) | Trust boundaries, threat model and known limitations. |
| [Contributing](docs/contributing.md) | Development setup, tests and review expectations. |

## License

AgentForge is licensed under [Apache-2.0](LICENSE). Third-party dependencies retain
their own licenses. See [SECURITY.md](SECURITY.md) for vulnerability reporting.
