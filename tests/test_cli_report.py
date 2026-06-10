from __future__ import annotations
import shutil
import pandas as pd
import pytest
from typer.testing import CliRunner

from pkflow.cli import app
from .conftest import make_results

runner = CliRunner()
HAS_PANDOC = shutil.which("pandoc") is not None


def _params():
    return pd.DataFrame([
        {"name": "CL", "type": "theta", "estimate": 10.0, "se": 1.0, "rse_pct": 10.0},
    ])


def test_report_command_writes_markdown(tmp_path):
    make_results("run_a", ofv=99.9, parameters=_params()).save(tmp_path)
    result = runner.invoke(app, ["report", str(tmp_path), "--format", "md"])
    assert result.exit_code == 0, result.output
    md = (tmp_path / "report" / "report.md").read_text()
    assert "run_a" in md and "99.9" in md and "CL" in md


@pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not installed")
def test_report_command_docx(tmp_path):
    make_results("run_a", ofv=99.9, parameters=_params()).save(tmp_path)
    result = runner.invoke(app, ["report", str(tmp_path), "--format", "docx",
                                 "--out", str(tmp_path / "rpt")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "rpt" / "report.docx").exists()
