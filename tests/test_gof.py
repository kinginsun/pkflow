from __future__ import annotations
import pandas as pd
import pytest
from plotnine import ggplot

from pkflow.diagnostics import gof, save_gof
from .conftest import make_results


def _full_preds(n=20, with_mdv=False):
    d = {
        "DV":    [float(i) for i in range(n)],
        "PRED":  [i + 0.1 for i in range(n)],
        "IPRED": [i + 0.05 for i in range(n)],
        "CWRES": [((-1) ** i) * 0.5 for i in range(n)],
        "TIME":  list(range(n)),
    }
    if with_mdv:
        d["MDV"] = [0] * (n - 2) + [1, 1]
    return pd.DataFrame(d)


def test_gof_returns_four_panels():
    r = make_results("a", predictions=_full_preds())
    panels = gof(r)
    assert set(panels) == {"dv_vs_pred", "dv_vs_ipred", "cwres_vs_pred", "cwres_vs_time"}
    assert all(isinstance(p, ggplot) for p in panels.values())


def test_gof_raises_on_empty_predictions():
    r = make_results("a")  # empty predictions
    with pytest.raises(ValueError, match="empty"):
        gof(r)


def test_gof_raises_on_missing_columns():
    r = make_results("a", predictions=pd.DataFrame({"DV": [1], "PRED": [1]}))
    with pytest.raises(ValueError, match="missing required columns"):
        gof(r)


def test_gof_drops_mdv_rows():
    r = make_results("a", predictions=_full_preds(n=10, with_mdv=True))
    # build plot and inspect underlying data: 2 MDV=1 rows excluded
    panels = gof(r)
    assert len(panels["dv_vs_pred"].data) == 8


def test_save_gof_writes_four_pngs(tmp_path):
    r = make_results("a", predictions=_full_preds())
    written = save_gof(r, tmp_path)
    assert len(written) == 4
    for p in written:
        assert p.exists() and p.suffix == ".png"
