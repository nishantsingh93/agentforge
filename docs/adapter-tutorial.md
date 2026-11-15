# A proposal-only adapter

[`examples/inspection_adapter.py`](../examples/inspection_adapter.py) is a complete,
tested example. From the repository root after installation:

```sh
python -m examples.inspection_adapter
python -m pytest tests/unit/test_adapter_tutorial.py -q
```

The example prints an `AdapterPlan` containing one **dry-run** read proposal for
F01/F04. No fixture read, mutation or command occurs. Unknown scenario IDs produce
an empty plan and owner-review claim. Untrusted task text never selects a host path.

## Contract and ownership

Implement `AgentAdapter.propose(AdapterTask) -> AdapterPlan`. The task carries
immutable task/scenario IDs, instruction text and source text; it grants no tool
capability. Return at most 32 typed `ActionRequest` values with unique action and
idempotency IDs, matching arguments/target/capabilities, declared impact and a claim.
IDs in this example are derived from the task so retries of the same proposal are
stable; changing operation semantics needs a new identity. Claims remain untrusted.

The trusted coordinator owns scenario loading, policy context, gateway, executor,
trace collector and judge. `run_adapter` validates your output, submits requests
through the gateway, verifies receipts and stops after refusal/failure/uncertainty.
Do not call `FixtureExecutor` or `SandboxRunner` from the adapter, issue grants,
open host files, run shell commands or treat a model response as observed evidence.
The model/task/scenario text is data, not an authorization source.

## From a proposal to an evaluation

For real evaluations, the trusted application's `run_suite` accepts your adapter:

```python
from pathlib import Path

from examples.inspection_adapter import InspectionAdapter
from agentforge.core.runner import run_suite
from agentforge.providers.offline import OfflineProvider
from agentforge.sandbox.runner import SandboxConfig, SandboxRunner


# Supply operator-reviewed values; these are not taken from model/task text.
def evaluate(docker_host: str, image: str):
    return run_suite(
        root=Path("."),
        runs_root=Path("runs/tutorial"),
        scenario_ids=("F01",),
        adapter=InspectionAdapter(),
        sandbox=SandboxRunner(SandboxConfig(docker_host, image)),
        provider=OfflineProvider(),
        model="offline",
    )
```

This example deliberately does not call `evaluate`. Calling it requires the approved
Docker environment; the coordinator may perform its own required checks even when
adapter proposals are dry-run. The inspection-only adapter makes no repair and is
not expected to receive Bullseye or PASS. Implement repairs by returning typed
fixture edit/check proposals and letting trusted gateway wiring authorize them;
never add a host-shell shortcut. The shipped CLI selects only its two demo adapters;
custom adapters are supplied through the Python API, not a dynamic plugin loader.

Test refusal, unsupported tasks, repeated IDs, malformed output, missing evidence
and untrusted instruction handling. Existing driver/gateway tests exercise stopped
submission and blocked-before-execution behavior. Keep dry-run by default until
execution has explicit task scope; setting `dry_run=False` is only a request and
cannot grant permission. Inspect actual receipts, checks and independent outcomes.

Installed Python adapters remain trusted host code. This protocol limits accidental
capability exposure, not malicious imports; do not install arbitrary untrusted
adapter packages alongside credentials. A separately isolated plugin host is outside
v0.1 scope. Read [security review](security.md) and [gateway semantics](gateway.md).
