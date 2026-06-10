from __future__ import annotations
from datetime import datetime
from pathlib import Path
import time
import typer

from . import __version__, backends, config, state
from .compare import build_table, overlay_gof
from .diagnostics import save_gof, save_vpc, save_shrinkage, save_eta_covariates
from .executors import LocalExecutor
from .model import Results
from .report import render as render_report
from .workflows import bootstrap as run_bootstrap

app = typer.Typer(add_completion=False, help="Pharmacometric modeling workflow CLI")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pkflow {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show pkflow version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Pharmacometric modeling workflow CLI."""


def _new_run_dir(root: Path, model_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = root / f"{model_path.stem}_{ts}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def _resolve_run_dir(run_dir: Path | None, *, require_results: bool = True) -> Path:
    """Pick up the last successful run when omitted, then validate.

    Validation: the path must exist and be a directory. When
    `require_results=True` (default), it must also contain `results.yaml`
    — that's what every consumer except `collect` needs.

    Bail out cleanly (no Python traceback) on any failure.
    """
    if run_dir is None:
        cfg = config.load()
        last = state.get_last_run(Path(cfg["runs_dir"]))
        if last is None:
            typer.secho(
                "no run directory given and no previous successful run recorded.\n"
                "  pass <run_dir> explicitly, or do `pkflow run <model>` first.",
                fg="red", err=True,
            )
            raise typer.Exit(code=2)
        typer.secho(f"(using last run: {last})", fg="cyan", err=True)
        run_dir = last

    if not run_dir.exists():
        typer.secho(f"✗ run directory does not exist: {run_dir}", fg="red", err=True)
        raise typer.Exit(code=2)
    if not run_dir.is_dir():
        typer.secho(f"✗ not a directory: {run_dir}", fg="red", err=True)
        raise typer.Exit(code=2)
    if require_results and not (run_dir / "results.yaml").exists():
        typer.secho(
            f"✗ not a pkflow run directory (missing results.yaml): {run_dir}\n"
            f"  if NONMEM artifacts (.lst/.ext) are present, try: pkflow collect {run_dir}",
            fg="red", err=True,
        )
        raise typer.Exit(code=2)
    return run_dir


@app.command()
def parse(model_path: Path):
    """Parse a model file and print its summary."""
    cfg = config.load()
    be = backends.get(cfg["backend"])
    m = be.parse(model_path)
    typer.echo(f"backend  : {m.backend}")
    typer.echo(f"name     : {m.stem}")
    typer.echo(f"dataset  : {m.dataset}")


@app.command()
def run(
    model_path: Path,
    backend: str = typer.Option(None, help="Override backend"),
    runs_dir: Path = typer.Option(None, help="Where to place the run directory"),
):
    """Run a model: copy → execute → collect → write results.yaml."""
    cfg = config.load()
    be = backends.get(backend or cfg["backend"])
    executor = LocalExecutor(cfg)

    run_dir = _new_run_dir(runs_dir or Path(cfg["runs_dir"]), model_path)
    typer.echo(f"→ {run_dir}")

    m = be.parse(model_path)
    t0 = time.time()
    handle = be.run(m, run_dir, executor)
    results = be.collect(m, run_dir, handle)
    results.duration_s = time.time() - t0
    results.save(run_dir)

    if results.status == "failed":
        typer.secho(f"✗ run failed ({results.duration_s:.1f}s)", fg="red", err=True)
        if results.error_log:
            typer.echo("", err=True)
            typer.echo(results.error_log, err=True)
        typer.echo("", err=True)
        typer.secho(f"  full log: {run_dir}/", fg="yellow", err=True)
        raise typer.Exit(code=1)

    # Stamp last-successful-run marker for downstream commands to default to.
    state.set_last_run(runs_dir or Path(cfg["runs_dir"]), run_dir)
    typer.echo(f"status: {results.status}  ofv: {results.ofv}  ({results.duration_s:.1f}s)")


@app.command()
def collect(run_dir: Path = typer.Argument(None)):
    """Re-collect results from an existing run directory (no re-run).

    Omit <run_dir> to use the last successful run.
    """
    # collect *creates* results.yaml from raw NONMEM artifacts, so don't require it.
    run_dir = _resolve_run_dir(run_dir, require_results=False)
    cfg = config.load()
    be = backends.get(cfg["backend"])
    # Find original .ctl in the run dir
    ctls = list(run_dir.glob("*.ctl")) + list(run_dir.glob("*.mod"))
    if not ctls:
        raise typer.BadParameter(f"no .ctl/.mod found in {run_dir}")
    m = be.parse(ctls[0])
    from .backends.base import RunHandle
    r = be.collect(m, run_dir, RunHandle(run_dir=run_dir, returncode=0))
    r.save(run_dir)
    typer.echo(f"ofv: {r.ofv}  params: {len(r.parameters)}")


@app.command()
def show(run_dir: Path = typer.Argument(None)):
    """Pretty-print a saved results.yaml.

    Omit <run_dir> to use the last successful run.
    """
    run_dir = _resolve_run_dir(run_dir)
    r = Results.load(run_dir)
    typer.echo(f"run      : {r.run_id}")
    typer.echo(f"backend  : {r.backend}")
    typer.echo(f"status   : {r.status}")
    typer.echo(f"ofv      : {r.ofv}")
    typer.echo(f"aic/bic  : {r.aic} / {r.bic}")
    typer.echo(f"cond #   : {r.condition_number}")
    if not r.parameters.empty:
        typer.echo("\nparameters:")
        typer.echo(r.parameters.to_string(index=False))


@app.command()
def diagnose(
    run_dir: Path = typer.Argument(None),
    out: Path = typer.Option(None, help="Output dir (default: <run_dir>/diagnostics)"),
):
    """Generate GOF plots from a saved run. Omit <run_dir> to use the last run."""
    run_dir = _resolve_run_dir(run_dir)
    r = Results.load(run_dir)
    out_dir = out or (run_dir / "diagnostics")
    written = save_gof(r, out_dir)
    for p in written:
        typer.echo(f"  {p}")
    typer.echo(f"→ {len(written)} plot(s) in {out_dir}")


@app.command()
def vpc(
    run_dir: Path = typer.Argument(None),
    n_sim: int = typer.Option(500, help="Number of simulation replicates"),
    n_bins: int = typer.Option(10, help="Number of time bins"),
    seed: int = typer.Option(1234),
    out: Path = typer.Option(None, help="Output dir (default: <run_dir>/diagnostics)"),
):
    """Simulate from the fitted model and produce a VPC plot.
    Omit <run_dir> to use the last successful run."""
    run_dir = _resolve_run_dir(run_dir)
    cfg = config.load()
    be = backends.get(cfg["backend"])
    executor = LocalExecutor(cfg)

    r = Results.load(run_dir)
    out_dir = out or (run_dir / "diagnostics")
    png = save_vpc(r, be, run_dir, executor, out_dir,
                   n_sim=n_sim, n_bins=n_bins, seed=seed)
    typer.echo(f"→ {png}")


@app.command()
def compare(
    run_dirs: list[Path] = typer.Argument(..., help="Two or more run directories"),
    sort: str = typer.Option(None, help="Sort table by a column (e.g. ofv, aic)"),
    gof: bool = typer.Option(False, help="Also write an overlaid DV-vs-PRED plot"),
    out: Path = typer.Option(Path("compare"), help="Output dir for csv/png"),
):
    """Compare saved runs: fit table (+ optional overlaid GOF). No re-run."""
    results = []
    for d in run_dirs:
        if not (d / "results.yaml").exists():
            typer.secho(f"  skip {d} (no results.yaml)", fg=typer.colors.YELLOW)
            continue
        results.append(Results.load(d))

    if len(results) < 2:
        raise typer.BadParameter(
            f"need at least 2 runs with results.yaml, found {len(results)}"
        )

    table = build_table(results, sort_by=sort)
    typer.echo(table.to_string(index=False))

    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "comparison.csv"
    table.to_csv(csv_path, index=False)
    typer.echo(f"\n→ {csv_path}")

    if gof:
        png = out / "compare_gof.png"
        overlay_gof(results).save(png, dpi=120, width=7, height=5,
                                  units="in", verbose=False)
        typer.echo(f"→ {png}")


@app.command()
def bootstrap(
    model_path: Path,
    n: int = typer.Option(200, help="Number of bootstrap replicates"),
    seed: int = typer.Option(1234),
    ci: float = typer.Option(0.95, help="Confidence level for percentile CIs"),
    backend: str = typer.Option(None, help="Override backend"),
    runs_dir: Path = typer.Option(None, help="Where to place the run directory"),
):
    """Case-resampling bootstrap: refit on N resampled datasets, report CIs."""
    cfg = config.load()
    be = backends.get(backend or cfg["backend"])
    executor = LocalExecutor(cfg)

    run_dir = _new_run_dir(runs_dir or Path(cfg["runs_dir"]), model_path)
    typer.echo(f"→ {run_dir}  ({n} replicates)")

    # Fit the original model once for the point estimates we bootstrap around
    model = be.parse(model_path)
    handle = be.run(model, run_dir, executor)
    original = be.collect(model, run_dir, handle)

    result = run_bootstrap(model, original, be, executor, run_dir,
                           n=n, seed=seed, level=ci)

    typer.echo(f"converged: {result.n_success}/{result.n_total}")
    typer.echo(f"\n{result.summary.to_string(index=False)}")
    typer.echo(f"\n→ {run_dir / 'bootstrap' / 'bootstrap_summary.csv'}")


@app.command()
def shrinkage(
    run_dir: Path = typer.Argument(None),
    threshold: float = typer.Option(0.30, help="Flag shrinkage above this fraction"),
    out: Path = typer.Option(None, help="Output dir (default: <run_dir>/diagnostics)"),
):
    """η/ε shrinkage table + η distribution plot. Omit <run_dir> to use last run."""
    run_dir = _resolve_run_dir(run_dir)
    r = Results.load(run_dir)
    out_dir = out or (run_dir / "diagnostics")
    written = save_shrinkage(r, out_dir, threshold=threshold)
    from .diagnostics import shrinkage_table
    typer.echo(shrinkage_table(r, threshold).to_string(index=False))
    typer.echo("")
    for p in written:
        typer.echo(f"→ {p}")


@app.command()
def etacov(
    run_dir: Path = typer.Argument(None),
    cov: list[str] = typer.Option(None, "--cov", help="Covariate column(s); default auto-detect"),
    out: Path = typer.Option(None, help="Output dir (default: <run_dir>/diagnostics)"),
):
    """η vs covariate plots. Omit <run_dir> to use the last successful run."""
    run_dir = _resolve_run_dir(run_dir)
    r = Results.load(run_dir)
    out_dir = out or (run_dir / "diagnostics")
    written = save_eta_covariates(r, out_dir, cols=cov or None)
    for p in written:
        typer.echo(f"→ {p}")


@app.command()
def report(
    run_dir: Path = typer.Argument(None),
    fmt: str = typer.Option("md", "--format", help="Output format: md, html, docx, or pdf"),
    gof: bool = typer.Option(False, help="Generate GOF plots first, then embed them"),
    out: Path = typer.Option(None, help="Output dir (default: <run_dir>/report)"),
):
    """Render a run report. Omit <run_dir> to use the last successful run."""
    run_dir = _resolve_run_dir(run_dir)
    r = Results.load(run_dir)
    if gof:
        save_gof(r, run_dir / "diagnostics")
    out_dir = out or (run_dir / "report")
    try:
        path = render_report(r, run_dir, out_dir, fmt=fmt)
    except (ValueError, RuntimeError) as e:
        typer.secho(f"✗ {e}", fg="red", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"→ {path}")


## ---------------------------------------------------------------------------
## config — view / set / unset / path
## ---------------------------------------------------------------------------
config_app = typer.Typer(help="View or edit pkflow configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show():
    """Show the resolved config with the source of each value."""
    rows = config.load_with_sources()
    width = max(len(k) for k in rows)
    typer.echo(f"{'key':<{width}}  value  (source)")
    typer.echo("-" * (width + 30))
    for k, (v, src) in rows.items():
        color = {"default": "white", "user": "cyan", "project": "green"}[src]
        typer.echo(f"{k:<{width}}  ", nl=False)
        typer.secho(f"{v}", fg=color, nl=False)
        typer.echo(f"  ({src})")
    typer.echo("")
    typer.echo(f"user file:    {config.user_config_path()}")
    typer.echo(f"project file: {config.project_config_path()}")


@config_app.command("get")
def config_get(key: str):
    """Print one resolved value."""
    cfg = config.load()
    if key not in cfg:
        typer.secho(f"unknown key: {key}", fg="red", err=True)
        raise typer.Exit(code=1)
    typer.echo(cfg[key])


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    project: bool = typer.Option(
        False, "--project",
        help="Write to ./pkflow.toml (default: ~/.config/pkflow/config.toml)",
    ),
):
    """Set a config key. Default scope is user-global."""
    scope = "project" if project else "user"
    try:
        path = config.set_value(key, value, scope=scope)
    except KeyError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"→ {path}")
    typer.echo(f"  {key} = {value}  ({scope})")


@config_app.command("unset")
def config_unset(
    key: str,
    project: bool = typer.Option(False, "--project", help="Remove from project file"),
):
    """Remove a key from the user or project config file."""
    scope = "project" if project else "user"
    path = config.unset_value(key, scope=scope)
    typer.echo(f"→ {path}  (removed {key})")


@config_app.command("path")
def config_path(
    project: bool = typer.Option(False, "--project", help="Print project path"),
):
    """Print the path of the config file (user by default)."""
    p = config.project_config_path() if project else config.user_config_path()
    typer.echo(p)


if __name__ == "__main__":
    app()
