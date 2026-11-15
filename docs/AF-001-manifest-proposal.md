# AF-001: approved package manifest

Approved by the user on 2026-11-06 and applied verbatim to `pyproject.toml`.
The proposal below is retained as the approval record.

Approval scope: create only the root `pyproject.toml` with the exact contents
below, then install the project with its development extras in a local virtual
environment and run AF-001 checks. No CI workflow, lockfile, policy, gateway,
sandbox, credential, or deployment changes are included.

The build backend is setuptools. Typer is the only direct runtime dependency;
future-ticket dependencies will be proposed when needed. Development extras
provide pytest, Ruff, mypy, and the Python build frontend. Version ranges constrain
major upgrades but are not a reproducibility lock. Installation downloads and
executes third-party packaging code; it requires the usual package supply-chain
trust. Removing the manifest and disposable virtual environment reverses setup.

```toml
[build-system]
requires = ["setuptools>=77,<81"]
build-backend = "setuptools.build_meta"

[project]
name = "agentforge"
version = "0.1.0.dev0"
description = "A local-first evaluation lab for AI engineering agents"
readme = "README.md"
requires-python = ">=3.12"
dependencies = ["typer>=0.16,<1"]

[project.optional-dependencies]
dev = [
    "pytest>=8,<10",
    "ruff>=0.11,<1",
    "mypy>=1.15,<2",
    "build>=1.2,<2",
]

[project.scripts]
agentforge = "agentforge.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-config --strict-markers"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]
```

CI proposal (separate approval, not applied): a future PR workflow would install
development extras, run pytest, Ruff, mypy and build, with read-only repository
permissions and no secrets. Exact workflow implementation is deferred.
