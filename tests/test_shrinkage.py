from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from plotnine import ggplot

from pkflow.diagnostics.shrinkage import (
    shrinkage_table, eta_distributions, save_shrinkage,
)
from .conftest import make_results


def _etas(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ETA(1)": rng.normal(0, 0.4, n),
        "ETA(2)": rng.normal(0, 0.05, n),  # heavily shrunk
    })


# ---- shrinkage_table -----------------------------------------------------
def test_table_rows_from_eta_shrinkage():
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.10, "ETA(2)": 0.45})
    t = shrinkage_table(r).set_index("parameter")
    assert set(t.index) == {"ETA(1)", "ETA(2)"}
    assert t.loc["ETA(1)", "kind"] == "eta"
    assert t.loc["ETA(1)", "shrinkage_pct"] == pytest.approx(10.0)
    assert t.loc["ETA(2)", "shrinkage_pct"] == pytest.approx(45.0)


def test_table_high_flag_uses_threshold():
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.10, "ETA(2)": 0.45})
    t = shrinkage_table(r, threshold=0.3).set_index("parameter")
    assert t.loc["ETA(1)", "high"] == False
    assert t.loc["ETA(2)", "high"] == True


def test_table_custom_threshold():
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.10})
    t = shrinkage_table(r, threshold=0.05).set_index("parameter")
    assert t.loc["ETA(1)", "high"] == True


def test_table_includes_eps_with_kind():
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.1},
                     eps_shrinkage={"EPS(1)": 0.2})
    t = shrinkage_table(r).set_index("parameter")
    assert t.loc["EPS(1)", "kind"] == "eps"


def test_table_raises_when_no_shrinkage():
    with pytest.raises(ValueError):
        shrinkage_table(make_results("a"))


# ---- eta_distributions ---------------------------------------------------
def test_eta_distributions_returns_ggplot():
    r = make_results("a", etas=_etas())
    p = eta_distributions(r)
    assert isinstance(p, ggplot)


def test_eta_distributions_covers_all_etas():
    r = make_results("a", etas=_etas())
    p = eta_distributions(r)
    assert set(p.data["eta"].unique()) == {"ETA(1)", "ETA(2)"}


def test_eta_distributions_raises_when_no_etas():
    with pytest.raises(ValueError):
        eta_distributions(make_results("a"))


# ---- save_shrinkage ------------------------------------------------------
def test_save_writes_table_and_plot(tmp_path):
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.1, "ETA(2)": 0.4},
                     etas=_etas())
    written = save_shrinkage(r, tmp_path)
    assert (tmp_path / "shrinkage_table.csv").exists()
    assert (tmp_path / "eta_distributions.png").exists()
    assert any(p.suffix == ".png" for p in written)


def test_save_table_only_when_no_etas(tmp_path):
    r = make_results("a", eta_shrinkage={"ETA(1)": 0.1})
    save_shrinkage(r, tmp_path)
    assert (tmp_path / "shrinkage_table.csv").exists()
    assert not (tmp_path / "eta_distributions.png").exists()
