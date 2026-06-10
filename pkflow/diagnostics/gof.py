"""Goodness-of-fit plots.

Pure functions of a `Results` object. The standard 4-panel GOF:
    1. DV   vs PRED   — population fit
    2. DV   vs IPRED  — individual fit
    3. CWRES vs PRED  — residual structure across predicted concentration
    4. CWRES vs TIME  — residual structure over time

All plots return a `plotnine.ggplot` so callers (notebook, CLI, report) can
display, save, or further compose. `save_gof()` is the CLI convenience.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plotnine import (
    ggplot, aes, geom_point, geom_abline, geom_hline, geom_smooth,
    labs, theme_minimal, facet_wrap,
)

from ..model import Results

REQUIRED_COLS = {"DV", "PRED", "IPRED", "CWRES", "TIME"}


# ---------------------------------------------------------------------------
# individual panels
# ---------------------------------------------------------------------------
def _scatter_with_identity(df: pd.DataFrame, x: str, y: str, title: str):
    return (
        ggplot(df, aes(x=x, y=y))
        + geom_point(alpha=0.4, size=1.2)
        + geom_abline(intercept=0, slope=1, linetype="dashed", color="red")
        + geom_smooth(method="loess", se=False, color="blue", size=0.7)
        + labs(title=title, x=x, y=y)
        + theme_minimal()
    )


def _scatter_residuals(df: pd.DataFrame, x: str, title: str):
    return (
        ggplot(df, aes(x=x, y="CWRES"))
        + geom_point(alpha=0.4, size=1.2)
        + geom_hline(yintercept=0, linetype="dashed", color="red")
        + geom_hline(yintercept=[-2, 2], linetype="dotted", color="grey")
        + geom_smooth(method="loess", se=False, color="blue", size=0.7)
        + labs(title=title, x=x, y="CWRES")
        + theme_minimal()
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def gof(results: Results, *, drop_mdv: bool = True) -> dict[str, "ggplot"]:
    """Return a dict of {panel_name: ggplot} for the 4-panel GOF.

    Filters out MDV>0 rows by default (dosing/missing observations don't have
    meaningful residuals).
    """
    df = results.predictions
    if df.empty:
        raise ValueError(
            "results.predictions is empty — did the run produce a $TABLE with "
            "DV/PRED/IPRED/CWRES/TIME columns?"
        )

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"predictions missing required columns for GOF: {sorted(missing)}. "
            f"Have: {sorted(df.columns)}"
        )

    if drop_mdv and "MDV" in df.columns:
        df = df[df["MDV"] == 0]
    if "EVID" in df.columns:
        df = df[df["EVID"] == 0]

    return {
        "dv_vs_pred":    _scatter_with_identity(df, "PRED", "DV", "DV vs PRED"),
        "dv_vs_ipred":   _scatter_with_identity(df, "IPRED", "DV", "DV vs IPRED"),
        "cwres_vs_pred": _scatter_residuals(df, "PRED", "CWRES vs PRED"),
        "cwres_vs_time": _scatter_residuals(df, "TIME", "CWRES vs TIME"),
    }


def save_gof(results: Results, out_dir: Path, *, dpi: int = 120) -> list[Path]:
    """Render all GOF panels to PNG. Returns list of written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = gof(results)
    written = []
    for name, p in plots.items():
        path = out_dir / f"{name}.png"
        p.save(path, dpi=dpi, width=6, height=4.5, units="in", verbose=False)
        written.append(path)
    return written
