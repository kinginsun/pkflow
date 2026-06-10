from __future__ import annotations
import numpy as np
import pandas as pd
from typer.testing import CliRunner

from pkflow.cli import app
from .conftest import make_results

runner = CliRunner()


def _results():
    ids = list(range(1, 21))
    etas = pd.DataFrame({"ETA(1)": np.random.default_rng(0).normal(0, 0.4, 20)},
                        index=pd.Index(ids, name="ID"))
    covs = pd.DataFrame({"ID": ids, "WT": np.linspace(60, 90, 20)})
    return make_results("run_a", etas=etas, covariates=covs)


def test_etacov_command_writes_png_and_csv(tmp_path):
    _results().save(tmp_path)
    result = runner.invoke(app, ["etacov", str(tmp_path), "--out", str(tmp_path / "d")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "d" / "eta_covariates.png").exists()
    assert (tmp_path / "d" / "eta_covariates.csv").exists()


def test_etacov_command_errors_without_covariates(tmp_path):
    make_results("run_a", ofv=1.0).save(tmp_path)
    result = runner.invoke(app, ["etacov", str(tmp_path), "--out", str(tmp_path / "d")])
    assert result.exit_code != 0
