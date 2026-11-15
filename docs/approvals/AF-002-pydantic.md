# AF-002 Pydantic dependency proposal — approved

The user approved this exact proposal on 2026-11-06; applied to the manifest.

Exact proposed edit to `pyproject.toml`:

```diff
-dependencies = ["typer>=0.16,<1"]
+dependencies = ["typer>=0.16,<1", "pydantic>=2.12,<3"]
```

Scope: apply this one edit, install its resolved dependencies into the existing
local `.venv`, and verify AF-002 plus the existing AF-001 checks. No lockfile or
other manifest settings change. Pydantic v2 implements the strict model and JSON
Schema contracts required by the specification; 2.12+ supports this Python 3.14
development environment. Installation includes compiled pydantic-core and its
typing dependencies. Risks are third-party package supply-chain trust and an
unlocked version range. The package is used for validation only, with no network
provider, command execution, or policy decisions. Removal of the new dependency
and AF-002 source reverses the change. Future dependency approvals are separate.
