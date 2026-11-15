# Local sandbox setup attempt and operator handoff

The user's “lets do it” on 2026-11-09 authorizes setting up the disposable local
Docker environment and obtaining an official Python image for AF-004 checks.
This extends the earlier implementation-only scope; no repeat approval is needed
for this setup. It does not authorize production access or broader permission edits.

Read AGENTS.md, the AF-004 plan/design, current runner requirements and checkpoint.
Checked Apple Silicon macOS and Homebrew availability; Docker/Colima are absent.
Attempted the standard installation:

```sh
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install colima docker
```

Exit **1**: this agent session cannot write Homebrew's directories under
`/opt/homebrew` and the user's Homebrew cache/log directories. No successful
installation, VM launch, image pull or container tests occurred. Do not follow
Homebrew's generic recursive ownership-change suggestion for this session boundary.
No privileged retry or alternative tool was used to bypass it.

## Prepared operator command

Run this in a normal macOS Terminal, outside the restricted agent session:

```sh
cd /Users/nishantsingh/Documents/code/agentforge
.venv/bin/python scripts/setup_local_sandbox.py
```

The script installs missing Colima/Docker tools via Homebrew, creates a separate
profile under `~/.colima-agentforge`, disables host mounts, SSH agent forwarding,
SSH config edits and default-context activation, and starts a 2 CPU / 2 GiB VM.
It refuses incompatible existing dedicated configuration instead of overwriting it.
The disk is configured for 10 GiB; Colima may also allocate its default root disk.

Using an explicit local socket and empty Docker configuration, it pulls the
official `docker.io/library/python:3.12-slim-bookworm` image, records the resolved
digest, checks Linux/no declared volumes, and runs the real integration tests.
The official publisher is a trust assumption, not a security audit. Network access
is needed for installation and image download; fixture containers retain the
approved no-network profile. Image validation and digest pinning are separate
from the later independent outcome oracles.

Logs, commands/exit codes, digest/socket settings and JUnit XML go into a unique
`runs/local-sandbox-setup/<timestamp>/` directory. Zero skipped integration tests
are required for the script's success result. It never marks AF-004 verified
automatically. The next worker must review evidence and update the ticket tracker.
The dedicated VM remains running and the script prints its scoped stop command.
No existing default VM is stopped/deleted and no global prune is performed.

## Checks performed here

- `.venv/bin/python scripts/setup_local_sandbox.py --check-only`: exit 2;
  Homebrew found, Colima/Docker absent. This mode changes nothing.
- `.venv/bin/python -m mypy scripts/setup_local_sandbox.py`: exit 0.
- Ruff formatting/lint checked; initial long-line findings corrected.
- In-process profile validation check passed: approved settings accepted; host
  mounts, agent forwarding, automatic context activation and altered CPU allocation
  rejected. No installation or VM command was executed during that check.
- Full setup execution remains unverified because of the installation boundary.
  No container-isolation success is claimed.

Files changed: new operator script and this handoff; tracker/resume updated with
the real blocker. Sandbox implementation, dependency manifest and existing tests
are unchanged. Next dependency remains AF-005 only after real AF-004 verification.

References checked for the setup design:
[Colima installation](https://colima.run/docs/installation/),
[configuration](https://colima.run/docs/configuration/), and
[command options](https://colima.run/docs/commands/).
