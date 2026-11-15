# AF-003 YAML dependencies — approved

Approved by the user on 2026-11-09 and applied exactly as proposed below.

Exact proposed edits to `pyproject.toml`:

```diff
-dependencies = ["typer>=0.16,<1", "pydantic>=2.12,<3"]
+dependencies = ["typer>=0.16,<1", "pydantic>=2.12,<3", "PyYAML>=6.0.3,<7"]
@@
     "build>=1.2,<2",
+    "types-PyYAML>=6,<7",
```

Scope: apply these two additions and install resolved dependencies in `.venv`.
PyYAML supplies the scenario YAML parser; types-PyYAML supplies typing information
for strict mypy. No lockfile or other manifest edits. Risks: package supply-chain
trust and parser exposure to untrusted YAML. The loader will use SafeLoader and
reject aliases, duplicate keys, non-string keys, excessive size/nesting, and
non-JSON values before strict Scenario validation. It will never evaluate YAML
tags or scenario-defined commands. Fixture access is read-only and digest pinned.
No sandbox, policy, CI, or deployment changes are included in this approval.
