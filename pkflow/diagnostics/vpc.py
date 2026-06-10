"""Visual Predictive Check.

Algorithm (backend-agnostic):
    1. Bin observations by TIME (equal-count or user-supplied edges).
    2. For the observed data: compute the 5/50/95 percentile per bin.
    3. For each simulated replicate: compute 5/50/95 per bin.
    4. Across replicates per bin: take the 2.5/97.5 percentile of each
       simulated percentile → "prediction interval" ribbons.
    5. Plot: observed lines overlaid on simulated CI ribbons.

This module knows nothing about NONMEM/Stan/mMdl. It consumes two DataFrames:
    observed:  ID, TIME, DV  (already filtered to EVID=0/MDV=0)
    simulated: REPLICATE, ID, TIME, DV
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from plotnine import (
    ggplot, aes, geom_ribbon, geom_line, geom_point,
    labs, theme_minimal, scale_y_log10,
)

from ..model import Results
from ..backends.base import Backend

LO, MED, HI = 0.05, 0.50, 0.95
CI_LO, CI_HI = 0.025, 0.975


# ---------------------------------------------------------------------------
# binning
# ---------------------------------------------------------------------------
def _bin_edges(times: pd.Series, n_bins: int) -> np.ndarray:
    """Equal-count bin edges over the unique time grid."""
    qs = np.linspace(0, 1, n_bins + 1)
    return np.unique(np.quantile(times, qs))


def _assign_bins(df: pd.DataFrame, edges: np.ndarray) -> pd.DataFrame:
    df = df.copy()
    idx = np.clip(np.searchsorted(edges, df["TIME"], side="right") - 1, 0, len(edges) - 2)
    df["BIN"] = idx
    # midpoint of bin for x-axis
    mids = (edges[:-1] + edges[1:]) / 2
    df["TBIN"] = mids[idx]
    return df


# ---------------------------------------------------------------------------
# percentile machinery
# ---------------------------------------------------------------------------
def _pctiles_per_bin(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    g = df.groupby(group_cols)["DV"]
    out = pd.DataFrame({
        "p_lo":  g.quantile(LO),
        "p_med": g.quantile(MED),
        "p_hi":  g.quantile(HI),
    }).reset_index()
    return out


def compute_vpc(
    observed: pd.DataFrame,
    simulated: pd.DataFrame,
    n_bins: int = 10,
) -> pd.DataFrame:
    """Returns one row per bin with observed percentiles + simulated CI bands.

    Columns: TBIN, obs_lo, obs_med, obs_hi,
             sim_lo_lo, sim_lo_hi, sim_med_lo, sim_med_hi, sim_hi_lo, sim_hi_hi
    """
    edges = _bin_edges(observed["TIME"], n_bins)
    obs = _assign_bins(observed, edges)
    sim = _assign_bins(simulated, edges)

    obs_p = _pctiles_per_bin(obs, ["BIN"]).rename(
        columns={"p_lo": "obs_lo", "p_med": "obs_med", "p_hi": "obs_hi"}
    )

    # Per-replicate percentiles, then CI across replicates
    sim_per_rep = _pctiles_per_bin(sim, ["REPLICATE", "BIN"])
    rows = []
    for bin_idx, grp in sim_per_rep.groupby("BIN"):
        rows.append({
            "BIN": bin_idx,
            "sim_lo_lo":  grp["p_lo"].quantile(CI_LO),
            "sim_lo_hi":  grp["p_lo"].quantile(CI_HI),
            "sim_med_lo": grp["p_med"].quantile(CI_LO),
            "sim_med_hi": grp["p_med"].quantile(CI_HI),
            "sim_hi_lo":  grp["p_hi"].quantile(CI_LO),
            "sim_hi_hi":  grp["p_hi"].quantile(CI_HI),
        })
    sim_ci = pd.DataFrame(rows)

    # Attach bin midpoints
    mids = (edges[:-1] + edges[1:]) / 2
    tbin = pd.DataFrame({"BIN": range(len(mids)), "TBIN": mids})

    return tbin.merge(obs_p, on="BIN", how="left").merge(sim_ci, on="BIN", how="left")


# ---------------------------------------------------------------------------
# plot
# ---------------------------------------------------------------------------
def plot_vpc(vpc_df: pd.DataFrame, *, log_y: bool = False) -> "ggplot":
    p = (
        ggplot(vpc_df, aes(x="TBIN"))
        # 90% PI ribbons (lower & upper observed percentiles)
        + geom_ribbon(aes(ymin="sim_lo_lo", ymax="sim_lo_hi"),
                      fill="blue", alpha=0.25)
        + geom_ribbon(aes(ymin="sim_hi_lo", ymax="sim_hi_hi"),
                      fill="blue", alpha=0.25)
        # 50% (median) ribbon
        + geom_ribbon(aes(ymin="sim_med_lo", ymax="sim_med_hi"),
                      fill="red", alpha=0.35)
        # Observed percentiles
        + geom_line(aes(y="obs_lo"), linetype="dashed", color="black")
        + geom_line(aes(y="obs_med"), color="black", size=0.9)
        + geom_line(aes(y="obs_hi"), linetype="dashed", color="black")
        + labs(title="VPC", x="Time", y="DV (observed vs simulated 5/50/95%)")
        + theme_minimal()
    )
    if log_y:
        p = p + scale_y_log10()
    return p


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------
def vpc(
    results: Results,
    backend: Backend,
    run_dir: Path,
    executor,
    *,
    n_sim: int = 500,
    n_bins: int = 10,
    seed: int = 1234,
) -> tuple[pd.DataFrame, "ggplot"]:
    """End-to-end: simulate via backend, compute VPC stats, return (df, plot)."""
    obs = results.predictions
    if obs.empty or not {"ID", "TIME", "DV"}.issubset(obs.columns):
        raise ValueError("results.predictions must have ID/TIME/DV for VPC")
    if "MDV" in obs.columns:
        obs = obs[obs["MDV"] == 0]
    if "EVID" in obs.columns:
        obs = obs[obs["EVID"] == 0]

    # Load model (need raw for simulation)
    model = backend.parse(results.model_path)
    sim = backend.simulate(model, results, run_dir, executor, n_sim=n_sim, seed=seed)

    vpc_df = compute_vpc(obs[["ID", "TIME", "DV"]], sim, n_bins=n_bins)
    return vpc_df, plot_vpc(vpc_df)


def save_vpc(
    results: Results,
    backend: Backend,
    run_dir: Path,
    executor,
    out_dir: Path,
    **kwargs,
) -> Path:
    df, plot = vpc(results, backend, run_dir, executor, **kwargs)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "vpc.csv", index=False)
    png = out_dir / "vpc.png"
    plot.save(png, dpi=120, width=7, height=5, units="in", verbose=False)
    return png
