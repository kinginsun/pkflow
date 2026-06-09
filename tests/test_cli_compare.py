from __future__ import annotations
import pandas as pd
from typer.testing import CliRunner

from pyrana.cli import app
from .conftest import make_results

runner = CliRunner()


def _save_run(tmp_path, run_id, **kw):
    d = tmp_path / run_id
    d.mkdir()
    make_results(run_id, **kw).save(d)
    return d


def test_compare_prints_table_and_writes_csv(tmp_path):
    a = _save_run(tmp_path, "run_a", ofv=100.0)
    b = _save_run(tmp_path, "run_b", ofv=90.0)
    out = tmp_path / "cmp"

    result = runner.invoke(app, ["compare", str(a), str(b), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert "run_a" in result.output and "run_b" in result.output
    csv = pd.read_csv(out / "comparison.csv")
    assert set(csv["run_id"]) == {"run_a", "run_b"}


def test_compare_skips_dirs_without_results(tmp_path):
    a = _save_run(tmp_path, "run_a", ofv=100.0)
    b = _save_run(tmp_path, "run_b", ofv=90.0)
    empty = tmp_path / "not_a_run"
    empty.mkdir()

    result = runner.invoke(
        app, ["compare", str(a), str(b), str(empty), "--out", str(tmp_path / "o")]
    )
    assert result.exit_code == 0, result.output
    assert "skip" in result.output


def test_compare_errors_with_fewer_than_two_valid_runs(tmp_path):
    a = _save_run(tmp_path, "run_a", ofv=100.0)
    result = runner.invoke(app, ["compare", str(a), "--out", str(tmp_path / "o")])
    assert result.exit_code != 0


def test_compare_gof_writes_png(tmp_path):
    preds_a = pd.DataFrame({"DV": [1, 2], "PRED": [1.1, 2.1], "TIME": [0, 1]})
    preds_b = pd.DataFrame({"DV": [1, 2], "PRED": [0.9, 1.8], "TIME": [0, 1]})
    a = _save_run(tmp_path, "run_a", ofv=100.0, predictions=preds_a)
    b = _save_run(tmp_path, "run_b", ofv=90.0, predictions=preds_b)
    out = tmp_path / "cmp"

    result = runner.invoke(
        app, ["compare", str(a), str(b), "--gof", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "compare_gof.png").exists()
