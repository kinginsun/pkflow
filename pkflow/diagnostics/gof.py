"""Goodness-of-fit plots.

Pure functions of a `Results` object. The standard 4-panel GOF:
    1. DV   vs PRED   — population fit
    2. DV   vs IPRED  — individual fit
    3. CWRES vs PRED  — residual structure across predicted concentration
    4. CWRES vs TIME  — residual structure over time

`gof()` returns each panel as a separate plotnine figure for notebooks.
`save_gof()` writes a single 2×2 PNG (`gof.png`) for CLI / reports.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from plotnine import (
    aes,
    geom_abline,
    geom_hline,
    geom_point,
    geom_smooth,
    ggplot,
    labs,
    theme_minimal,
)

from skmisc.loess import loess

from ..model import Results

REQUIRED_COLS = {"DV", "PRED", "IPRED", "CWRES", "TIME"}


def _prepare_gof_df(results: Results, *, drop_mdv: bool = True) -> pd.DataFrame:
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
    return df


# ---------------------------------------------------------------------------
# individual panels (plotnine — notebook API)
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


def _loess_line(ax, x, y, *, color: str = "blue") -> None:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 4:
        return
    order = np.argsort(x)
    x, y = x[order], y[order]
    for span in (0.3, 0.5, 0.75):
        try:
            model = loess(x, y, span=span, iterations=0)
            model.fit()
            fitted = model.predict(x)
            ax.plot(x, fitted.values, color=color, linewidth=0.7)
            return
        except ValueError:
            continue


def _plot_identity_panel(ax, df: pd.DataFrame, x: str, y: str, title: str) -> None:
    ax.scatter(df[x], df[y], alpha=0.4, s=12, edgecolors="none")
    lo = float(min(df[x].min(), df[y].min()))
    hi = float(max(df[x].max(), df[y].max()))
    ax.plot([lo, hi], [lo, hi], linestyle="--", color="red", linewidth=1)
    _loess_line(ax, df[x].values, df[y].values)
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(y)


def _plot_residual_panel(ax, df: pd.DataFrame, x: str, title: str) -> None:
    ax.scatter(df[x], df["CWRES"], alpha=0.4, s=12, edgecolors="none")
    ax.axhline(0, linestyle="--", color="red", linewidth=1)
    for level in (-2, 2):
        ax.axhline(level, linestyle=":", color="grey", linewidth=1)
    _loess_line(ax, df[x].values, df["CWRES"].values)
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel("CWRES")


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def gof(results: Results, *, drop_mdv: bool = True) -> dict[str, "ggplot"]:
    """Return a dict of {panel_name: ggplot} for the 4-panel GOF."""
    df = _prepare_gof_df(results, drop_mdv=drop_mdv)
    return {
        "dv_vs_pred": _scatter_with_identity(df, "PRED", "DV", "DV vs PRED"),
        "dv_vs_ipred": _scatter_with_identity(df, "IPRED", "DV", "DV vs IPRED"),
        "cwres_vs_pred": _scatter_residuals(df, "PRED", "CWRES vs PRED"),
        "cwres_vs_time": _scatter_residuals(df, "TIME", "CWRES vs TIME"),
    }


def save_gof(results: Results, out_dir: Path, *, dpi: int = 120) -> list[Path]:
    """Render the 4-panel GOF as one 2×2 PNG (`gof.png`). Returns written paths."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    df = _prepare_gof_df(results)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    _plot_identity_panel(axes[0, 0], df, "PRED", "DV", "DV vs PRED")
    _plot_identity_panel(axes[0, 1], df, "IPRED", "DV", "DV vs IPRED")
    _plot_residual_panel(axes[1, 0], df, "PRED", "CWRES vs PRED")
    _plot_residual_panel(axes[1, 1], df, "TIME", "CWRES vs TIME")

    path = out_dir / "gof.png"
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return [path]
