from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from plotnine import ggplot

from pkflow.diagnostics.vpc import (
    _bin_edges, _assign_bins, compute_vpc, plot_vpc, save_vpc,
    vpc as run_vpc,
)
from .conftest import make_results


def _observed(n_id=10, n_t=5, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_id):
        for t in range(n_t):
            rows.append({"ID": i, "TIME": float(t), "DV": float(rng.normal(10 - t, 1))})
    return pd.DataFrame(rows)


def _simulated(observed, n_rep=50, seed=1):
    rng = np.random.default_rng(seed)
    frames = []
    for rep in range(1, n_rep + 1):
        df = observed.copy()
        df["DV"] = df["DV"] + rng.normal(0, 1, len(df))
        df["REPLICATE"] = rep
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---- binning -------------------------------------------------------------
def test_bin_edges_count_and_monotonic():
    edges = _bin_edges(pd.Series(range(100)), n_bins=10)
    assert len(edges) == 11
    assert list(edges) == sorted(edges)


def test_assign_bins_adds_bin_and_tbin():
    df = pd.DataFrame({"TIME": [0.0, 1.0, 2.0, 3.0], "DV": [1, 2, 3, 4]})
    edges = np.array([0.0, 2.0, 4.0])
    out = _assign_bins(df, edges)
    assert "BIN" in out and "TBIN" in out
    assert out["BIN"].tolist() == [0, 0, 1, 1]


# ---- compute -------------------------------------------------------------
def test_compute_vpc_one_row_per_bin():
    obs = _observed()
    sim = _simulated(obs)
    out = compute_vpc(obs, sim, n_bins=5)
    assert len(out) == 5
    for col in ("TBIN", "obs_lo", "obs_med", "obs_hi",
                "sim_med_lo", "sim_med_hi"):
        assert col in out.columns


def test_compute_vpc_ci_band_brackets_nothing_negative_width():
    obs = _observed()
    sim = _simulated(obs)
    out = compute_vpc(obs, sim, n_bins=5)
    assert (out["sim_med_hi"] >= out["sim_med_lo"]).all()


# ---- plot ----------------------------------------------------------------
def test_plot_vpc_returns_ggplot():
    obs = _observed()
    out = compute_vpc(obs, _simulated(obs), n_bins=5)
    assert isinstance(plot_vpc(out), ggplot)


def test_plot_vpc_log_y_option():
    obs = _observed()
    out = compute_vpc(obs, _simulated(obs), n_bins=5)
    assert isinstance(plot_vpc(out, log_y=True), ggplot)


# ---- orchestrator with a fake backend ------------------------------------
class _FakeBackend:
    name = "fake"

    def __init__(self, sim_df):
        self._sim = sim_df

    def parse(self, path):
        return object()

    def simulate(self, model, results, run_dir, executor, n_sim=500, seed=1234):
        return self._sim


def test_vpc_orchestrator_returns_df_and_plot(tmp_path):
    obs = _observed()
    sim = _simulated(obs)
    r = make_results("a", predictions=obs.assign(MDV=0))
    be = _FakeBackend(sim)
    df, plot = run_vpc(r, be, tmp_path, executor=None, n_sim=50, n_bins=5)
    assert isinstance(plot, ggplot)
    assert len(df) == 5


def test_vpc_raises_without_id_time_dv():
    r = make_results("a", predictions=pd.DataFrame({"TIME": [1], "DV": [1]}))
    with pytest.raises(ValueError):
        run_vpc(r, _FakeBackend(pd.DataFrame()), None, None)


def test_save_vpc_writes_csv_and_png(tmp_path):
    obs = _observed()
    r = make_results("a", predictions=obs.assign(MDV=0))
    be = _FakeBackend(_simulated(obs))
    png = save_vpc(r, be, tmp_path, None, tmp_path / "out", n_sim=50, n_bins=5)
    assert png.exists()
    assert (tmp_path / "out" / "vpc.csv").exists()
