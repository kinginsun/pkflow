from __future__ import annotations
import pandas as pd
import pytest
from plotnine import ggplot

from pkflow.compare import build_table, overlay_gof
from .conftest import make_results


def _preds(dv, pred, mdv=None):
    d = {"DV": dv, "PRED": pred, "TIME": list(range(len(dv)))}
    if mdv is not None:
        d["MDV"] = mdv
    return pd.DataFrame(d)


def test_build_table_one_row_per_run():
    table = build_table([
        make_results("run_a", ofv=100.0),
        make_results("run_b", ofv=90.0),
    ])
    assert list(table["run_id"]) == ["run_a", "run_b"]
    assert len(table) == 2


def test_delta_ofv_is_relative_to_best():
    table = build_table([
        make_results("run_a", ofv=100.0),
        make_results("run_b", ofv=90.0),  # best (lowest)
        make_results("run_c", ofv=95.0),
    ]).set_index("run_id")
    assert table.loc["run_b", "delta_ofv"] == 0.0
    assert table.loc["run_a", "delta_ofv"] == 10.0
    assert table.loc["run_c", "delta_ofv"] == 5.0


def test_n_params_counts_parameter_rows():
    table = build_table([
        make_results("run_a", ofv=1.0, n_params=4),
        make_results("run_b", ofv=2.0, n_params=7),
    ]).set_index("run_id")
    assert table.loc["run_a", "n_params"] == 4
    assert table.loc["run_b", "n_params"] == 7


def test_run_with_no_ofv_has_none_delta():
    table = build_table([
        make_results("run_a", ofv=100.0),
        make_results("run_b", ofv=None, status="failed"),
    ]).set_index("run_id")
    assert pd.isna(table.loc["run_b", "ofv"])
    assert pd.isna(table.loc["run_b", "delta_ofv"])
    # best OFV ignores the failed run
    assert table.loc["run_a", "delta_ofv"] == 0.0


def test_overlay_gof_returns_ggplot():
    p = overlay_gof([
        make_results("run_a", ofv=1.0, predictions=_preds([1, 2], [1.1, 2.1])),
        make_results("run_b", ofv=2.0, predictions=_preds([1, 2], [0.9, 1.8])),
    ])
    assert isinstance(p, ggplot)


def test_overlay_gof_labels_rows_by_run_id():
    p = overlay_gof([
        make_results("run_a", ofv=1.0, predictions=_preds([1, 2], [1.1, 2.1])),
        make_results("run_b", ofv=2.0, predictions=_preds([1], [0.9])),
    ])
    counts = p.data["run_id"].value_counts().to_dict()
    assert counts == {"run_a": 2, "run_b": 1}


def test_overlay_gof_drops_mdv_rows():
    p = overlay_gof([
        make_results("run_a", ofv=1.0, predictions=_preds([1, 2, 3], [1, 2, 3], mdv=[0, 1, 0])),
        make_results("run_b", ofv=2.0, predictions=_preds([1, 2], [1, 2], mdv=[0, 0])),
    ])
    # run_a's MDV=1 row is excluded
    assert p.data["run_id"].value_counts().to_dict() == {"run_a": 2, "run_b": 2}


def test_overlay_gof_raises_when_a_run_lacks_predictions():
    with pytest.raises(ValueError):
        overlay_gof([
            make_results("run_a", ofv=1.0, predictions=_preds([1], [1])),
            make_results("run_b", ofv=2.0),  # no predictions
        ])


def test_sort_by_ofv_orders_ascending():
    table = build_table([
        make_results("run_a", ofv=100.0),
        make_results("run_b", ofv=90.0),
        make_results("run_c", ofv=95.0),
    ], sort_by="ofv")
    assert list(table["run_id"]) == ["run_b", "run_c", "run_a"]


def test_sort_by_unknown_column_raises():
    with pytest.raises(ValueError):
        build_table([
            make_results("run_a", ofv=1.0),
            make_results("run_b", ofv=2.0),
        ], sort_by="nonsense")


def test_fewer_than_two_runs_raises():
    with pytest.raises(ValueError):
        build_table([make_results("run_a", ofv=1.0)])


def test_empty_list_raises():
    with pytest.raises(ValueError):
        build_table([])
