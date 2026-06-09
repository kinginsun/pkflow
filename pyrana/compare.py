"""Cross-run comparison.

Pure functions over a list of `Results`. `build_table()` produces a tidy
DataFrame ranking runs by fit; `overlay_gof()` overlays each run's DV-vs-PRED
on one figure. The CLI `compare` command wraps these with `Results.load`.

Consumes only saved `Results` — no backend, no re-run.
"""
from __future__ import annotations
import pandas as pd
from plotnine import (
    ggplot, aes, geom_point, geom_abline, labs, theme_minimal,
)

from .model import Results

# Column order for the comparison table.
COLUMNS = [
    "run_id", "status", "ofv", "delta_ofv",
    "n_params", "aic", "bic", "condition_number",
]


def build_table(results: list[Results], *, sort_by: str | None = None) -> pd.DataFrame:
    """One row per run: status, OFV, ΔOFV vs best, #params, AIC/BIC, cond#.

    ΔOFV is relative to the lowest OFV in the set; runs without an OFV
    (e.g. failed) get NaN for both ofv and delta_ofv and are excluded from
    the "best" calculation. `sort_by` orders by any table column (ascending,
    NaNs last).
    """
    if sort_by is not None and sort_by not in COLUMNS:
        raise ValueError(
            f"unknown sort column {sort_by!r}; choose from {COLUMNS}"
        )
    if len(results) < 2:
        raise ValueError(
            f"need at least 2 runs to compare, got {len(results)}"
        )

    ofvs = [r.ofv for r in results if r.ofv is not None]
    best = min(ofvs) if ofvs else None

    rows = []
    for r in results:
        rows.append({
            "run_id": r.run_id,
            "status": r.status,
            "ofv": r.ofv,
            "delta_ofv": (r.ofv - best) if (r.ofv is not None and best is not None) else None,
            "n_params": len(r.parameters),
            "aic": r.aic,
            "bic": r.bic,
            "condition_number": r.condition_number,
        })
    table = pd.DataFrame(rows, columns=COLUMNS)
    if sort_by is not None:
        table = table.sort_values(sort_by, na_position="last").reset_index(drop=True)
    return table


def overlay_gof(results: list[Results]) -> ggplot:
    """Overlay every run's DV-vs-PRED on one figure, colored by run_id.

    Each run must have a non-empty `predictions` table with DV and PRED
    columns. MDV>0 / EVID>0 rows are dropped (no meaningful prediction).
    """
    if len(results) < 2:
        raise ValueError(f"need at least 2 runs to overlay, got {len(results)}")

    frames = []
    for r in results:
        df = r.predictions
        if df.empty or not {"DV", "PRED"}.issubset(df.columns):
            raise ValueError(
                f"run {r.run_id!r} has no predictions with DV/PRED columns; "
                "run `pyrana diagnose`/collect a $TABLE first"
            )
        if "MDV" in df.columns:
            df = df[df["MDV"] == 0]
        if "EVID" in df.columns:
            df = df[df["EVID"] == 0]
        frames.append(df.assign(run_id=r.run_id))

    data = pd.concat(frames, ignore_index=True)
    return (
        ggplot(data, aes(x="PRED", y="DV", color="run_id"))
        + geom_point(alpha=0.4, size=1.2)
        + geom_abline(intercept=0, slope=1, linetype="dashed", color="black")
        + labs(title="DV vs PRED — run comparison",
               x="PRED", y="DV", color="run")
        + theme_minimal()
    )
