# AF-006 — Adapter protocol and demo patcher: implementation plan

Implemented and verified after AF-005 real integration passed.
This is the original design; final behavior and evidence are in AF-006.md.

## Read and ownership

Read project plan, AGENTS.md, STATUS.json, RESUME.md, AF-005 handoff,
core schemas/trace/evidence/scenario/fixtures, sandbox integration tests,
F01 scenario, owned orders fixture and existing unit-test patterns.
Contracts are strict and versioned; fixture snapshots are immutable bytes;
collectors distinguish claims from executor observations. No adapter package exists.

## Design and files

- adapters/base.py: strict immutable AdapterTask and adapter output contracts;
  structural AgentAdapter protocol. AdapterTask provides scenario ID, task text,
  and immutable source text supplied by trusted runner. No filesystem paths with
  host capability, collector, sandbox runner, or credentials are handed to adapters.
- adapters/demo_patcher.py: deterministic demo for the owned null-status fixture.
  It proposes typed read/edit/check actions; correct mode restores the null guard,
  flawed mode proposes a superficially plausible incomplete patch and a false
  success claim. Mode is explicitly labeled, not a semantic model judgment.
  Unexpected source causes triage; no blanket string rewriting of arbitrary code.
- adapters/session.py: bounded driver accepts an adapter and a submission interface
  (the gateway abstraction), forwarding requests and recording claims through
  trusted wiring. No executor implementation or automatic approval. Until AF-008,
  test doubles return not-executed observations; demo traces never invent commands.
- tests/unit/test_adapters.py: swap adapter implementations; inspect submitted typed
  requests; assert no direct sandbox/host execution; bounds and malformed outputs;
  stop on denied requests; distinguish flawed claims from observed results; replay
  a demo trace through AF-005 collector.
- docs/adapters.md and docs/tickets/AF-006.md: public contract, limitations, checks.

Boundary choice: a pure request/response adapter avoids passing an executable
callback carrying hidden executor capabilities into adapter code. Trusted session
wiring owns gateway submission and trace recording. Protocol types alone cannot
contain malicious Python imports; supported adapters are trusted package code,
while scenario instructions and future model outputs are untrusted data. Separate
process confinement of arbitrary third-party Python is outside this ticket.

## Validation / risk

Run full pytest, strict mypy, lint, formatting and package build. Preserve existing
schema and sandbox tests. No manifests, policy decisions, sandbox profiles or
production integrations change. If actual gateway authorization logic becomes
necessary, stop at the interface and seek scoped approval rather than implement it
under this ticket. AF-007 follows after AF-006; AF-008 supplies real dispatch.
