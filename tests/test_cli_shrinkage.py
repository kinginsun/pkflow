from __future__ import annotations
import numpy as np
import pandas as pd
from typer.testing import CliRunner

from pyrana.cli import app
from .conftest import make_results

runner = CliRunner()


def test_shrinkage_command_prints_table_and_writes_files(tmp_path):
    etas = pd.DataFrame({"ETA(1)": np.random.default_rng(0).normal(0, 0.4, 30)})
    make_results("run_a", eta_shrinkage={"ETA(1)": 0.12, "ETA(2)": 0.40},
                 etas=etas).save(tmp_path)

    result = runner.invoke(app, ["shrinkage", str(tmp_path), "--out", str(tmp_path / "d")])

    assert result.exit_code == 0, result.output
    assert "ETA(1)" in result.output
    assert (tmp_path / "d" / "shrinkage_table.csv").exists()
    assert (tmp_path / "d" / "eta_distributions.png").exists()


def test_shrinkage_command_errors_without_shrinkage(tmp_path):
    make_results("run_a", ofv=1.0).save(tmp_path)
    result = runner.invoke(app, ["shrinkage", str(tmp_path), "--out", str(tmp_path / "d")])
    assert result.exit_code != 0
