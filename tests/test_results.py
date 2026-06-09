from __future__ import annotations
import pandas as pd

from pyrana.model import Results
from .conftest import make_results


def test_save_load_roundtrip_metadata(tmp_path):
    r = make_results("run_a", ofv=123.4, aic=130.0, bic=140.0,
                     condition_number=12.5, n_params=3)
    r.save(tmp_path)
    loaded = Results.load(tmp_path)
    assert loaded.run_id == "run_a"
    assert loaded.backend == "nonmem"
    assert loaded.status == "ok"
    assert loaded.ofv == 123.4
    assert loaded.aic == 130.0
    assert loaded.bic == 140.0
    assert loaded.condition_number == 12.5


def test_save_load_roundtrip_parameters(tmp_path):
    r = make_results("run_a", ofv=1.0, n_params=3)
    r.save(tmp_path)
    loaded = Results.load(tmp_path)
    pd.testing.assert_frame_equal(loaded.parameters, r.parameters)


def test_save_writes_results_yaml(tmp_path):
    make_results("run_a", ofv=1.0).save(tmp_path)
    assert (tmp_path / "results.yaml").exists()


def test_load_missing_optional_frames_gives_empty(tmp_path):
    # no predictions/etas saved → loaded as empty DataFrames, not errors
    make_results("run_a", ofv=1.0).save(tmp_path)
    loaded = Results.load(tmp_path)
    assert loaded.predictions.empty
    assert loaded.etas.empty


def test_predictions_roundtrip(tmp_path):
    preds = pd.DataFrame({"DV": [1.0, 2.0], "PRED": [1.1, 1.9], "TIME": [0, 1]})
    r = make_results("run_a", ofv=1.0, predictions=preds)
    r.save(tmp_path)
    assert (tmp_path / "predictions.parquet").exists()
    pd.testing.assert_frame_equal(Results.load(tmp_path).predictions, preds)


def test_shrinkage_and_artifacts_roundtrip(tmp_path):
    from datetime import datetime
    from pathlib import Path
    r = make_results("run_a", ofv=1.0)
    r.eta_shrinkage = {"ETA(1)": 0.12, "ETA(2)": 0.30}
    r.artifacts = {"lst": Path("run_a.lst"), "ext": Path("run_a.ext")}
    r.save(tmp_path)
    loaded = Results.load(tmp_path)
    assert loaded.eta_shrinkage == {"ETA(1)": 0.12, "ETA(2)": 0.30}
    assert loaded.artifacts["lst"] == Path("run_a.lst")


def test_save_handles_numpy_scalar_fields(tmp_path):
    # pharmpy returns numpy scalars; yaml.safe_dump can't represent them.
    import numpy as np
    r = make_results("run_a")
    r.ofv = np.float64(68736.5)
    r.condition_number = np.float64(42.0)
    r.eta_shrinkage = {"ETA(1)": np.float64(0.2)}
    r.save(tmp_path)  # must not raise
    loaded = Results.load(tmp_path)
    assert loaded.ofv == 68736.5
    assert loaded.condition_number == 42.0
    assert loaded.eta_shrinkage == {"ETA(1)": 0.2}


def test_covariates_roundtrip(tmp_path):
    covs = pd.DataFrame({"ID": [1, 2], "WT": [70.0, 85.0], "SEX": [0, 1]})
    r = make_results("run_a", ofv=1.0)
    r.covariates = covs
    r.save(tmp_path)
    assert (tmp_path / "covariates.parquet").exists()
    pd.testing.assert_frame_equal(Results.load(tmp_path).covariates, covs)


def test_covariates_default_empty(tmp_path):
    make_results("run_a", ofv=1.0).save(tmp_path)
    assert Results.load(tmp_path).covariates.empty


def test_started_at_roundtrips_as_datetime(tmp_path):
    from datetime import datetime
    make_results("run_a", ofv=1.0).save(tmp_path)
    loaded = Results.load(tmp_path)
    assert loaded.started_at == datetime(2026, 6, 9, 12, 0, 0)
