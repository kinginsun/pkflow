from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from types import SimpleNamespace
from pathlib import Path

from pkflow.workflows.bootstrap import (
    resample_subjects, percentile_ci, summarize_bootstrap,
    bootstrap, BootstrapResult,
)
from pkflow.model import Model
from .conftest import make_results


def _params(**name_to_est):
    return pd.DataFrame(
        [{"name": n, "type": "theta", "estimate": v} for n, v in name_to_est.items()]
    )


# ---- resample_subjects ---------------------------------------------------
def _dataset():
    # 3 subjects with distinct row counts: ID 1 -> 2 rows, 2 -> 3 rows, 3 -> 1 row
    return pd.DataFrame({
        "ID":   [1, 1, 2, 2, 2, 3],
        "TIME": [0, 1, 0, 1, 2, 0],
        "DV":   [10, 9, 20, 18, 16, 30],
    })


def test_resample_keeps_subject_count():
    out = resample_subjects(_dataset(), "ID", np.random.default_rng(0))
    assert out["ID"].nunique() == 3  # same number of subjects as input


def test_resample_relabels_to_unique_sequential_ids():
    out = resample_subjects(_dataset(), "ID", np.random.default_rng(0))
    ids = out["ID"].unique()
    # fresh sequential IDs, each block intact (no merging of duplicate draws)
    assert sorted(ids) == [1, 2, 3]
    for _id, block in out.groupby("ID"):
        assert (block["TIME"].values == sorted(block["TIME"].values)).all()


def test_resample_blocks_come_from_original_subjects():
    src = _dataset()
    out = resample_subjects(src, "ID", np.random.default_rng(0))
    # each resampled block's row count must match some original subject's count
    orig_counts = set(src.groupby("ID").size())
    for _id, block in out.groupby("ID"):
        assert len(block) in orig_counts


def test_resample_is_deterministic_with_seed():
    a = resample_subjects(_dataset(), "ID", np.random.default_rng(42))
    b = resample_subjects(_dataset(), "ID", np.random.default_rng(42))
    pd.testing.assert_frame_equal(a, b)


def test_resample_preserves_columns():
    out = resample_subjects(_dataset(), "ID", np.random.default_rng(0))
    assert list(out.columns) == ["ID", "TIME", "DV"]


# ---- percentile_ci -------------------------------------------------------
def test_percentile_ci_95():
    lo, hi = percentile_ci(np.arange(0, 101), level=0.95)
    assert lo == pytest.approx(2.5)
    assert hi == pytest.approx(97.5)


def test_percentile_ci_narrower_for_lower_level():
    vals = np.arange(0, 101)
    lo95, hi95 = percentile_ci(vals, 0.95)
    lo50, hi50 = percentile_ci(vals, 0.50)
    assert (hi50 - lo50) < (hi95 - lo95)


# ---- summarize_bootstrap -------------------------------------------------
def test_summarize_builds_one_row_per_parameter():
    original = make_results("orig", parameters=_params(CL=10.0, V=50.0))
    reps = [
        make_results("r1", parameters=_params(CL=11.0, V=52.0)),
        make_results("r2", parameters=_params(CL=9.0, V=48.0)),
        make_results("r3", parameters=_params(CL=10.0, V=50.0)),
    ]
    table = summarize_bootstrap(original, reps, level=0.95).set_index("name")
    assert set(table.index) == {"CL", "V"}
    assert table.loc["CL", "original_est"] == 10.0
    assert table.loc["CL", "boot_median"] == 10.0
    assert table.loc["CL", "n_success"] == 3
    assert table.loc["CL", "ci_lo"] <= table.loc["CL", "ci_hi"]


def test_summarize_excludes_non_converged_replicates():
    original = make_results("orig", parameters=_params(CL=10.0))
    reps = [
        make_results("r1", parameters=_params(CL=11.0)),
        make_results("r2", parameters=_params(CL=9.0)),
        make_results("bad", parameters=_params(CL=999.0), status="failed"),
    ]
    table = summarize_bootstrap(original, reps, level=0.95).set_index("name")
    assert table.loc["CL", "n_success"] == 2
    # the failed replicate's 999.0 must not influence the median
    assert table.loc["CL", "boot_median"] == pytest.approx(10.0)


def test_summarize_raises_when_no_successful_replicates():
    original = make_results("orig", parameters=_params(CL=10.0))
    reps = [make_results("bad", parameters=_params(CL=1.0), status="failed")]
    with pytest.raises(ValueError):
        summarize_bootstrap(original, reps, level=0.95)


# ---- orchestrator (fake backend) -----------------------------------------
class _FakeBackend:
    """Records calls; returns Results whose CL estimate shifts per replicate
    so the summary has real spread. One replicate is marked failed."""
    def __init__(self, fail_on=None):
        self.run_calls = 0
        self.fail_on = fail_on
        self.seen_row_counts = []

    def run(self, model, run_dir, executor):
        run_dir.mkdir(parents=True, exist_ok=True)
        self.run_calls += 1
        # prove the resampled dataset reached the backend
        self.seen_row_counts.append(sum(1 for _ in open(model.dataset)))
        return SimpleNamespace(run_dir=run_dir, returncode=0)

    def collect(self, model, run_dir, handle):
        i = self.run_calls
        status = "failed" if self.fail_on == i else "ok"
        return make_results(run_dir.name,
                            parameters=_params(CL=10.0 + i * 0.1),
                            status=status)


def _bootstrap_data():
    return pd.DataFrame({
        "ID":   [1, 1, 2, 2, 3, 3],
        "TIME": [0, 1, 0, 1, 0, 1],
        "DV":   [1, 2, 3, 4, 5, 6],
    })


def test_bootstrap_runs_n_replicates(tmp_path):
    model = Model(path=tmp_path / "m.ctl", backend="nonmem")
    (tmp_path / "m.ctl").write_text("$PROBLEM x\n")
    orig = make_results("orig", parameters=_params(CL=10.0))
    be = _FakeBackend()

    res = bootstrap(model, orig, be, executor=None, run_dir=tmp_path / "run",
                    n=5, seed=1, dataset=_bootstrap_data(), id_col="ID")

    assert isinstance(res, BootstrapResult)
    assert res.n_total == 5
    assert res.n_success == 5
    assert be.run_calls == 5
    assert "CL" in set(res.summary["name"])
    assert len(res.replicate_params) == 5  # one param row per replicate


def test_bootstrap_passes_resampled_data_to_backend(tmp_path):
    # resampled set has 3 subjects × 2 rows = 6 rows each replicate
    model = Model(path=tmp_path / "m.ctl", backend="nonmem")
    (tmp_path / "m.ctl").write_text("$PROBLEM x\n")
    be = _FakeBackend()
    bootstrap(model, make_results("orig", parameters=_params(CL=10.0)), be,
              executor=None, run_dir=tmp_path / "run", n=3, seed=1,
              dataset=_bootstrap_data(), id_col="ID")
    assert be.seen_row_counts == [6, 6, 6]


def test_bootstrap_cleans_up_replicate_dirs(tmp_path):
    model = Model(path=tmp_path / "m.ctl", backend="nonmem")
    (tmp_path / "m.ctl").write_text("$PROBLEM x\n")
    res = bootstrap(model, make_results("orig", parameters=_params(CL=10.0)),
                    _FakeBackend(), executor=None, run_dir=tmp_path / "run",
                    n=3, seed=1, dataset=_bootstrap_data(), id_col="ID")
    boot_dir = tmp_path / "run" / "bootstrap"
    # decision: replicate run dirs cleaned up, summary kept
    assert not list(boot_dir.glob("rep_*"))
    assert (boot_dir / "bootstrap_summary.csv").exists()


def test_bootstrap_counts_failed_replicates(tmp_path):
    model = Model(path=tmp_path / "m.ctl", backend="nonmem")
    (tmp_path / "m.ctl").write_text("$PROBLEM x\n")
    res = bootstrap(model, make_results("orig", parameters=_params(CL=10.0)),
                    _FakeBackend(fail_on=2), executor=None,
                    run_dir=tmp_path / "run", n=4, seed=1,
                    dataset=_bootstrap_data(), id_col="ID")
    assert res.n_total == 4
    assert res.n_success == 3  # replicate 2 failed
