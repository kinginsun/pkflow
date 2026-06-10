from __future__ import annotations
from pathlib import Path
from typer.testing import CliRunner

from pkflow.cli import app
from .conftest import make_results

runner = CliRunner()

TEMPLATE = Path(__file__).parent / "fixtures" / "004.mod"


def test_parse_command_prints_summary():
    result = runner.invoke(app, ["parse", str(TEMPLATE)])
    assert result.exit_code == 0, result.output
    assert "nonmem" in result.output
    assert "004" in result.output


def test_show_command_prints_saved_results(tmp_path):
    make_results("run_a", ofv=123.4, n_params=3).save(tmp_path)
    result = runner.invoke(app, ["show", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "run_a" in result.output
    assert "123.4" in result.output


def test_diagnose_command_writes_plots(tmp_path):
    import pandas as pd
    preds = pd.DataFrame({
        "DV": [float(i) for i in range(12)],
        "PRED": [i + 0.1 for i in range(12)],
        "IPRED": [i + 0.05 for i in range(12)],
        "CWRES": [((-1) ** i) * 0.4 for i in range(12)],
        "TIME": list(range(12)),
    })
    make_results("run_a", ofv=1.0, predictions=preds).save(tmp_path)
    out = tmp_path / "diag"
    result = runner.invoke(app, ["diagnose", str(tmp_path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert len(list(out.glob("*.png"))) == 4
