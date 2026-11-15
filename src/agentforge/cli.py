"""Registry inspection and disposable evaluation CLI."""

from pathlib import Path
from typing import Annotated

import typer

from agentforge.benchmarks.cli import app as benchmark_app

app = typer.Typer(
    name="agentforge",
    help="AgentForge — benchmark, evaluate, and govern AI engineering agents.",
    no_args_is_help=True,
    add_completion=False,
)
scenarios_app = typer.Typer(help="Inspect explicitly registered scenarios.")
app.add_typer(scenarios_app, name="scenarios")
app.add_typer(benchmark_app, name="benchmark")


@app.callback()
def main() -> None:
    """Provide the CLI command group without executing agent actions."""


@scenarios_app.command("list")
def scenarios_list(
    root: Annotated[Path, typer.Option(help="Project directory containing the registry.")] = Path(
        "."
    ),
) -> None:
    """List validated scenarios and verify their pinned fixtures."""
    try:
        from agentforge.core.scenario import load_registry

        entries = load_registry(root)
    except ModuleNotFoundError as error:
        if error.name != "yaml":
            raise
        typer.echo(
            "YAML dependency unavailable; install the approved project dependencies.", err=True
        )
        raise typer.Exit(3) from error
    except (OSError, ValueError) as error:
        typer.echo(f"Invalid registry: {error}", err=True)
        raise typer.Exit(2) from error
    for entry in entries:
        typer.echo(f"{entry.scenario.id}\t{entry.scenario.name}\t{entry.scenario.category}")


@app.command()
def validate(
    scenario: Annotated[str, typer.Option(help="Registered project-relative scenario YAML path.")],
    root: Annotated[Path, typer.Option(help="Project directory containing the registry.")] = Path(
        "."
    ),
) -> None:
    """Validate a registered scenario, fault reference and immutable fixture snapshot."""
    try:
        from agentforge.core.scenario import validate_registered

        entry = validate_registered(root, scenario)
    except ModuleNotFoundError as error:
        if error.name != "yaml":
            raise
        typer.echo(
            "YAML dependency unavailable; install the approved project dependencies.", err=True
        )
        raise typer.Exit(3) from error
    except (OSError, ValueError) as error:
        typer.echo(f"Invalid scenario: {error}", err=True)
        raise typer.Exit(2) from error
    typer.echo(f"Valid {entry.scenario.id}: {entry.scenario.fixture}")


@app.command()
def run(
    scenario: Annotated[
        str | None, typer.Option(help="Registered scenario ID (F01 or F04 for demo).")
    ] = None,
    suite: Annotated[str | None, typer.Option(help="Named suite: smoke (F01, F04).")] = None,
    offline: Annotated[
        bool, typer.Option(help="Run without model credentials; semantic judgments stay UNKNOWN.")
    ] = False,
    agent: Annotated[
        str, typer.Option(help="demo-patcher or demo-patcher-flawed.")
    ] = "demo-patcher",
    root: Annotated[Path, typer.Option(help="Project registry directory.")] = Path("."),
    runs_root: Annotated[Path, typer.Option(help="Fresh run artifacts directory.")] = Path("runs"),
    docker_host: Annotated[
        str | None,
        typer.Option(envvar="AGENTFORGE_DOCKER_HOST", help="Explicit local Unix Docker socket."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option(envvar="AGENTFORGE_IMAGE", help="Reviewed digest-pinned local image."),
    ] = None,
    preflight_retries: Annotated[
        int, typer.Option(min=0, max=2, help="Retry Docker preflight only; never retry actions.")
    ] = 0,
) -> None:
    """Run disposable evaluations, preserving unknowns and deterministic failures."""
    from agentforge.adapters.demo_patcher import DemoPatcher
    from agentforge.core.runner import SMOKE, run_suite
    from agentforge.providers.offline import OfflineProvider
    from agentforge.sandbox.runner import SandboxConfig, SandboxRunner, SandboxUnavailable

    if (scenario is None) == (suite is None):
        typer.echo("Choose exactly one of --scenario or --suite.", err=True)
        raise typer.Exit(2)
    if suite is not None and suite != "smoke":
        typer.echo("Unknown suite; supported suite: smoke.", err=True)
        raise typer.Exit(2)
    if agent not in {"demo-patcher", "demo-patcher-flawed"}:
        typer.echo("Unknown agent; supported: demo-patcher, demo-patcher-flawed.", err=True)
        raise typer.Exit(2)
    if scenario is not None and scenario not in SMOKE:
        typer.echo(
            "The scripted demo supports F01 and F04 only; "
            "use an adapter via the Python API for other scenarios.",
            err=True,
        )
        raise typer.Exit(2)
    if not offline:
        typer.echo(
            "Model provider unavailable: no network provider is installed. "
            "Use --offline for explicit UNKNOWN judgments.",
            err=True,
        )
        raise typer.Exit(3)
    if docker_host is None or image is None:
        typer.echo(
            "Docker configuration unavailable: set --docker-host and --image "
            "(or AGENTFORGE_DOCKER_HOST and AGENTFORGE_IMAGE). No host fallback.",
            err=True,
        )
        raise typer.Exit(3)
    try:
        sandbox = SandboxRunner(SandboxConfig(docker_host, image))
        result = run_suite(
            root=root,
            runs_root=runs_root,
            scenario_ids=SMOKE if suite else (str(scenario),),
            adapter=DemoPatcher("flawed" if agent.endswith("-flawed") else "correct", execute=True),
            sandbox=sandbox,
            provider=OfflineProvider(),
            model="offline",
            preflight_retries=preflight_retries,
        )
    except SandboxUnavailable as error:
        typer.echo(f"Docker unavailable: {error}", err=True)
        raise typer.Exit(3) from error
    except ValueError as error:
        typer.echo(f"Invalid run configuration: {error}", err=True)
        raise typer.Exit(2) from error
    except OSError as error:
        typer.echo("Run infrastructure unavailable; no action retry.", err=True)
        raise typer.Exit(3) from error
    for attempt in result.attempts:
        report = attempt.report
        typer.echo(
            f"{attempt.scenario_id} {attempt.run_id}: "
            + (
                f"quality={report.quality_status} safety={report.safety} "
                f"outcome={report.outcome.category if report.outcome else 'UNKNOWN'} "
                f"decision={report.release_decision}"
                if report
                else str(attempt.error)
            )
        )
    typer.echo(f"Summary: {runs_root / result.run_id / 'summary.json'}")
    raise typer.Exit(result.exit_code)


@app.command()
def report(
    run_id: str,
    format: Annotated[str, typer.Option(help="html or json; output to stdout.")] = "html",
    runs_root: Annotated[Path, typer.Option(help="Existing run artifact directory.")] = Path(
        "runs"
    ),
    baseline: Annotated[str | None, typer.Option(help="Optional baseline run or suite ID.")] = None,
) -> None:
    """Render validated artifacts offline; redirect stdout to a CI artifact file."""
    from agentforge.reporting.comparison import compare as compare_reports
    from agentforge.reporting.html_report import render_html
    from agentforge.reporting.json_report import load_report

    if format not in {"html", "json"}:
        typer.echo("Unsupported report format; choose html or json.", err=True)
        raise typer.Exit(2)
    try:
        document = load_report(runs_root, run_id)
        comparison = (
            compare_reports(load_report(runs_root, baseline), document) if baseline else None
        )
        rendered = (
            render_html(document, comparison)
            if format == "html"
            else (comparison or document).model_dump_json(indent=2)
        )
    except (OSError, ValueError):
        typer.echo(
            "Invalid or unavailable report artifacts; verify IDs, schemas and evidence.", err=True
        )
        raise typer.Exit(2) from None
    typer.echo(rendered)


@app.command()
def compare(
    baseline: str,
    current: str,
    runs_root: Annotated[Path, typer.Option(help="Existing run artifact directory.")] = Path(
        "runs"
    ),
) -> None:
    """Emit JSON baseline deltas with original counts, coverage and unknowns."""
    report(current, format="json", runs_root=runs_root, baseline=baseline)
