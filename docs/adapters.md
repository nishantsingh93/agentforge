# Adapter API

`AgentAdapter.propose(AdapterTask)` returns a bounded `AdapterPlan` of typed
requests and an explicitly untrusted claim. Tasks expose text only, no executor,
gateway, collector or filesystem handles. The current `DemoPatcher` supports the
owned F01/F04 snapshots in correct/flawed modes; unknown input produces triage.
Construction is dry-run by default. The run CLI explicitly opts into gateway
execution. No adapter proposal is itself evidence that anything ran.

The trusted `run_adapter` driver validates plans and action correspondence, records
claims/proposals, submits through `SubmissionGateway`, and verifies receipts against
the same trace. Refused, failed or uncertain receipts stop submission. Decision-only
stubs remain supported for tests; ALLOW alone is not execution evidence. Real
execution belongs exclusively to the gateway and its sandbox/simulator executor.
See [gateway](gateway.md) and [run orchestration](runs.md).

Supported adapters are trusted installed Python code. These interfaces limit
accidental capability exposure; they do not isolate arbitrary malicious imports.
Scenario/model text remains untrusted data. Adapters cannot submit observed tool
results through their plan contract or mint synthetic approval grants.

Start with the [tested adapter tutorial](adapter-tutorial.md). Custom adapters are
passed to `run_suite` through the Python API; the CLI exposes only the scripted demo
choices. No dynamic plugin loader or general host-shell tool is implemented.
