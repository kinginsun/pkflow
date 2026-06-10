from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from plotnine import ggplot

from pkflow.diagnostics.shrinkage import (
    eta_covariate_data, eta_covariate_plots, save_eta_covariates,
)
from .conftest import make_results


def _results_with_covs(n=30, seed=0):
    rng = np.random.default_rng(seed)
    ids = list(range(1, n + 1))
    etas = pd.DataFrame({"ETA(1)": rng.normal(0, 0.4, n),
                         "ETA(2)": rng.normal(0, 0.3, n)},
                        index=pd.Index(ids, name="ID"))
    covs = pd.DataFrame({"ID": ids,
                         "WT": rng.normal(75, 12, n),
                         "SEX": rng.integers(0, 2, n)})
    return make_results("a", etas=etas, covariates=covs)


# ---- eta_covariate_data --------------------------------------------------
def test_data_joins_etas_and_covariates():
    df = eta_covariate_data(_results_with_covs())
    assert {"ID", "eta", "eta_value", "covariate", "cov_value"} <= set(df.columns)
    assert set(df["eta"].unique()) == {"ETA(1)", "ETA(2)"}
    assert set(df["covariate"].unique()) == {"WT", "SEX"}


def test_data_respects_cols_filter():
    df = eta_covariate_data(_results_with_covs(), cols=["WT"])
    assert set(df["covariate"].unique()) == {"WT"}


def test_data_row_count():
    # n subjects × 2 etas × 2 covariates
    df = eta_covariate_data(_results_with_covs(n=10))
    assert len(df) == 10 * 2 * 2


# ---- eta_covariate_plots -------------------------------------------------
def test_plots_returns_ggplot():
    assert isinstance(eta_covariate_plots(_results_with_covs()), ggplot)


def test_plots_raises_without_covariates():
    r = make_results("a", etas=pd.DataFrame({"ETA(1)": [0.1, -0.1]}))
    with pytest.raises(ValueError):
        eta_covariate_plots(r)


def test_plots_raises_without_etas():
    r = make_results("a", covariates=pd.DataFrame({"ID": [1], "WT": [70]}))
    with pytest.raises(ValueError):
        eta_covariate_plots(r)


# ---- save_eta_covariates -------------------------------------------------
def test_save_writes_png_and_csv(tmp_path):
    written = save_eta_covariates(_results_with_covs(), tmp_path)
    assert (tmp_path / "eta_covariates.png").exists()
    assert (tmp_path / "eta_covariates.csv").exists()
    assert any(p.suffix == ".png" for p in written)
