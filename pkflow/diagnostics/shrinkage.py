"""η / ε shrinkage diagnostics.

Pure functions over a `Results`:
    - `shrinkage_table`  : tidy table of η/ε shrinkage with a high-shrinkage flag
    - `eta_distributions`: faceted histogram of individual η estimates

High shrinkage (conventionally > 30%) means individual estimates have
collapsed toward the population mean — EBE-based diagnostics (η-covariate
plots, IPRED GOF) become unreliable, so the table flags it.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plotnine import (
    ggplot, aes, geom_histogram, geom_vline, geom_hline, geom_point,
    geom_smooth, facet_grid, facet_wrap, labs, theme_minimal,
)

from ..model import Results

HIGH_SHRINKAGE = 0.30

_COLUMNS = ["parameter", "kind", "shrinkage", "shrinkage_pct", "high"]


def shrinkage_table(results: Results, threshold: float = HIGH_SHRINKAGE) -> pd.DataFrame:
    """One row per η/ε: shrinkage (fraction + %), flagged high above threshold."""
    rows = []
    for kind, shr in (("eta", results.eta_shrinkage), ("eps", results.eps_shrinkage)):
        for name, value in shr.items():
            rows.append({
                "parameter": name,
                "kind": kind,
                "shrinkage": float(value),
                "shrinkage_pct": float(value) * 100.0,
                "high": float(value) > threshold,
            })
    if not rows:
        raise ValueError(
            "no shrinkage data in results — did the run report η/ε shrinkage?"
        )
    return pd.DataFrame(rows, columns=_COLUMNS)


def eta_distributions(results: Results) -> ggplot:
    """Faceted histogram of individual η estimates, with a reference line at 0.

    A distribution piling up at 0 signals shrinkage toward the population mean.
    """
    etas = results.etas
    if etas.empty:
        raise ValueError(
            "results.etas is empty — no individual η estimates to plot"
        )
    long = etas.melt(value_vars=list(etas.columns), var_name="eta", value_name="value")
    return (
        ggplot(long, aes(x="value"))
        + geom_histogram(bins=20, fill="steelblue", color="white")
        + geom_vline(xintercept=0, linetype="dashed", color="red")
        + facet_wrap("eta", scales="free")
        + labs(title="Individual η distributions", x="η", y="count")
        + theme_minimal()
    )


def eta_covariate_data(results: Results, cols=None) -> pd.DataFrame:
    """Long table joining individual η estimates to per-subject covariates.

    Columns: ID, eta, eta_value, covariate, cov_value. The η index is taken as
    the subject id; covariates' first column is the id key.
    """
    etas, covs = results.etas, results.covariates
    if etas.empty:
        raise ValueError("results.etas is empty — no individual η estimates")
    if covs.empty:
        raise ValueError("results.covariates is empty — nothing to plot η against")

    id_col = covs.columns[0]
    e = etas.copy()
    e[id_col] = etas.index
    eta_long = e.melt(id_vars=[id_col], var_name="eta", value_name="eta_value")

    cov_cols = list(cols) if cols else [c for c in covs.columns if c != id_col]
    merged = eta_long.merge(covs[[id_col] + cov_cols], on=id_col)
    return merged.melt(
        id_vars=[id_col, "eta", "eta_value"],
        value_vars=cov_cols, var_name="covariate", value_name="cov_value",
    )


def eta_covariate_plots(results: Results, cols=None) -> ggplot:
    """η vs covariate scatter grid (η rows × covariate columns) with a linear
    trend. Categorical covariates show as points; boxplots are future work."""
    data = eta_covariate_data(results, cols)
    return (
        ggplot(data, aes(x="cov_value", y="eta_value"))
        + geom_point(alpha=0.5, size=1.2)
        + geom_hline(yintercept=0, linetype="dashed", color="grey")
        + geom_smooth(method="lm", se=False, color="red", size=0.7)
        + facet_grid("eta ~ covariate", scales="free_x")
        + labs(title="η vs covariates", x="covariate value", y="η")
        + theme_minimal()
    )


def save_eta_covariates(results: Results, out_dir: Path, cols=None,
                        *, dpi: int = 120) -> list[Path]:
    """Write eta_covariates.csv (long data) + eta_covariates.png."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = eta_covariate_data(results, cols)
    csv = out_dir / "eta_covariates.csv"
    data.to_csv(csv, index=False)
    png = out_dir / "eta_covariates.png"
    eta_covariate_plots(results, cols).save(
        png, dpi=dpi, width=8, height=6, units="in", verbose=False)
    return [csv, png]


def save_shrinkage(results: Results, out_dir: Path,
                   threshold: float = HIGH_SHRINKAGE, *, dpi: int = 120) -> list[Path]:
    """Write shrinkage_table.csv and (when η estimates exist) the η histogram."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    table = shrinkage_table(results, threshold)
    csv_path = out_dir / "shrinkage_table.csv"
    table.to_csv(csv_path, index=False)
    written.append(csv_path)

    if not results.etas.empty:
        png = out_dir / "eta_distributions.png"
        eta_distributions(results).save(png, dpi=dpi, width=7, height=4,
                                        units="in", verbose=False)
        written.append(png)
    return written
