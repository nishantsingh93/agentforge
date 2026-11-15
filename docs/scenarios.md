# Scenario registry

Install the project dependencies before loading YAML scenarios.
From the repository root:

```sh
agentforge scenarios list
agentforge validate --scenario scenarios/correctness/F01.yaml
```

Both commands accept `--root /path/to/project`. The root is an explicit trusted
user choice, not something read from scenario instructions. Only YAML paths in
`scenarios/registry.json` are loaded. Adding a loose YAML file does not register
it. Registry paths must stay below `scenarios/`; fixture directories below
`fixtures/`; fault references below `faults/`. Faults are read as inert bytes.
The loader does not apply patches, import fixtures, run commands, or judge them.

The registry requires schema version `1`, a unique `scenarios` list, and a
`fixtures` list of `reference`/`directory` objects. Each reference has the form
`order-service@sha256:<digest>`. Scenario fixture references must match a listed
reference exactly; floating tags are rejected. Duplicate IDs, paths, JSON/YAML
keys and fixture references are errors. YAML uses a SafeLoader subclass that
rejects aliases, merges, non-string keys, unknown tags, excess nesting/nodes,
non-JSON values and oversize inputs, followed by strict Scenario validation.

Fixture snapshots preserve canonical relative file paths and raw bytes. Symlinks,
hardlinks, FIFOs and other nonregular files are rejected. Per-file, per-tree and
whole-registry limits bound reads; captured bytes are immutable. The tree digest
is SHA256 of the UTF-8 encoding of compact, ASCII-escaped JSON containing sorted
`[relative_path, sha256_of_file_bytes]` pairs. File mode, timestamps and empty
directories are not part of the digest. No executable modes are carried in the
snapshot; sandbox materialization belongs to AF-004.

To calculate a digest for an intentionally reviewed fixture update:

```sh
python -c 'from pathlib import Path; from agentforge.core.fixtures import snapshot_fixture; print(snapshot_fixture(Path("."), "fixtures/order-service").digest)'
```

Update both registry and scenario references only when changing the fixture is
intentional. A mismatching hash fails validation rather than silently repinning.
Modifying a fixture after a snapshot leaves the snapshot unchanged; loading it
again rejects changed content against the old pin.

AF-013 expands the registry to F01–F10, with pinned data-only fault setup and
independent outcome profiles. See [failure-lab.md](failure-lab.md). [CLI run orchestration](runs.md) is implemented. F01 version 2 replaces the illustrative patch
reference with a bounded JSON replacement and disposable regression tests.
