# AF-001 handoff

Goal: scaffold the Python package and developer experience.
Status: implementation and acceptance checks verified on Python 3.14.8;
Git feature-branch workflow remains blocked by filesystem permissions.
Next dependency-ordered ticket: AF-002, versioned schemas.

## Read and plan

Read the Downloads and workspace copies of AGENTS.md and
AGENTFORGE_PROJECT_PLAN.md; comparison confirmed identical contents. Inspected
all scaffold source, tests, README, manifest proposal, and configuration. There
was no prior code or Git repository. The specification calls for a Python src
layout, Typer CLI, and separately owned future runtime/evaluation modules.
Scope stayed within AF-001: CLI shell, help/error tests, tooling, and docs.

## Changed files and rationale

- `src/agentforge/{__init__,__main__,cli}.py`: package and CLI entry points.
- `tests/unit/test_cli.py`: help succeeds; unknown commands return input error 2.
- `pyproject.toml`: approved package metadata, entry point, dependencies, pytest,
  Ruff, and strict mypy settings.
- `README.md`: setup/check commands and truthful offline evaluation roadmap.
- `.gitignore`: virtual environments, cache, build and run artifacts.
- `docs/AF-001-manifest-proposal.md`: exact approved manifest and risk assessment.
- This handoff: checks, observed limitations, and next ticket.

## Checks and evidence

Commands run from the project root unless noted. Final successful checks used
Python 3.14.8, Typer 0.28.0, pytest 9.2.0, Ruff 0.17.4, mypy 1.20.2,
build 1.6.1, and isolated setuptools 80.10.2.

| Command | Exit | Result |
| --- | --- | --- |
| `git status --short` | 128 | No Git repository |
| `git init -b af-001-scaffold` | 1 | `.git: Operation not permitted`; not bypassed |
| `cmp AGENTS.md /Users/nishantsingh/Downloads/AGENTS.md && cmp AGENTFORGE_PROJECT_PLAN.md /Users/nishantsingh/Downloads/AGENTFORGE_PROJECT_PLAN.md` | 0 | Specifications unchanged |
| `/opt/homebrew/bin/python3.14 -m venv .venv` | 0 | Local environment created |
| `.venv/bin/python -m pip install -e '.[dev]'` | 1 | PyPI DNS unavailable to pip |
| `.venv/bin/python -m pip install --no-index --find-links /private/tmp/agentforge-wheels -e '.[dev]'` | 0 | Editable install with all approved extras succeeded |
| `.venv/bin/agentforge --help` | 0 | Installed console entry point works |
| `.venv/bin/python -m agentforge --help` | 0 | Module entry point works |
| `.venv/bin/python -m pytest` | 0 | 2 tests passed |
| `.venv/bin/python -m ruff check .` | 0 | Lint passed |
| `.venv/bin/python -m ruff format --check .` | 0 final; 1 initially | Corrected trailing blank line and historical handoff code-block formatting; final check passed for 9 files |
| `.venv/bin/python -m mypy` | 0 | Strict typing passed for 4 source files |
| `.venv/bin/python -m pip check` | 0 | No broken requirements |
| `PIP_NO_INDEX=1 PIP_FIND_LINKS=/private/tmp/agentforge-wheels .venv/bin/python -m build` | 0 | sdist and wheel built in isolated build environments |
| `/opt/homebrew/bin/python3.14 -m venv /private/tmp/agentforge-wheel-check` | 0 | Clean wheel-test environment created |
| `/private/tmp/agentforge-wheel-check/bin/python -m pip install --no-index --find-links /private/tmp/agentforge-wheels dist/agentforge-0.1.0.dev0-py3-none-any.whl` | 0 | Built wheel installed with runtime dependencies |
| `/private/tmp/agentforge-wheel-check/bin/agentforge --help && /private/tmp/agentforge-wheel-check/bin/python -m agentforge --help` | 0 | Both wheel entry points work from `/private/tmp`, outside source tree |

Dependency download workaround: the permitted `curl` command fetched PyPI JSON
metadata and compatible wheels into `/private/tmp/agentforge-metadata` and
`/private/tmp/agentforge-wheels`. SHA256 hashes of every downloaded wheel matched
PyPI metadata before installation. Pip performed dependency resolution from that
local wheel directory; the approved manifest was not changed. Temporary resolver
script: `/private/tmp/agentforge-resolve.py`. No lockfile was created.

## Review, safety, and limitations

The user explicitly approved the manifest and local dependency installation on
2026-11-06. The applied manifest matches the proposal verbatim. No other protected
area was changed: no CI, auth, policy, gateway, sandbox, secrets or deployment
implementation. No production credentials or production integrations used.
Reviewed source/configuration directly because Git diff is unavailable. No tests
were removed or weakened. Existing specification files were preserved.

The CLI provides help only. Scenario execution, semantic judges, sandboxing and
reports belong to later tickets. Python 3.12 minimum-version runtime testing was
not performed because that interpreter is unavailable; the installed 3.14 runtime
passed the checks. CI is deferred and requires separate approval. The required
feature branch could not be created due to `.git` write restrictions; no commit
or remote publication was attempted.
