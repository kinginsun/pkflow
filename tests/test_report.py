from __future__ import annotations
import shutil
from pathlib import Path
import pandas as pd
import pytest

from pyrana.report.render import build_context, render_markdown, render
from .conftest import make_results

HAS_PANDOC = shutil.which("pandoc") is not None


def _params():
    return pd.DataFrame([
        {"name": "CL", "type": "theta", "estimate": 10.0, "se": 1.0, "rse_pct": 10.0},
        {"name": "V", "type": "theta", "estimate": 50.0, "se": 2.5, "rse_pct": 5.0},
    ])


def _results():
    return make_results("ad3tr4_run", ofv=123.45, aic=140.0, bic=150.0,
                        condition_number=12.3, parameters=_params())


# ---- build_context -------------------------------------------------------
def test_context_has_header_and_fit_stats(tmp_path):
    ctx = build_context(_results(), tmp_path)
    assert ctx["run_id"] == "ad3tr4_run"
    assert ctx["backend"] == "nonmem"
    assert ctx["status"] == "ok"
    assert ctx["ofv"] == 123.45
    assert ctx["aic"] == 140.0
    assert ctx["condition_number"] == 12.3


def test_context_parameters_carry_estimate_and_rse(tmp_path):
    ctx = build_context(_results(), tmp_path)
    by_name = {p["name"]: p for p in ctx["parameters"]}
    assert by_name["CL"]["estimate"] == 10.0
    assert by_name["CL"]["rse_pct"] == 10.0
    assert len(ctx["parameters"]) == 2


def test_context_collects_existing_plots(tmp_path):
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    (diag / "dv_vs_pred.png").write_bytes(b"\x89PNG")
    ctx = build_context(_results(), tmp_path)
    titles = {p["title"] for p in ctx["plots"]}
    assert "dv_vs_pred" in titles


def test_context_no_plots_when_absent(tmp_path):
    assert build_context(_results(), tmp_path)["plots"] == []


def test_context_includes_bootstrap_when_present(tmp_path):
    bdir = tmp_path / "bootstrap"
    bdir.mkdir()
    pd.DataFrame([{"name": "CL", "original_est": 10.0, "boot_median": 10.2,
                   "ci_lo": 8.5, "ci_hi": 11.9, "n_success": 200}]).to_csv(
        bdir / "bootstrap_summary.csv", index=False)
    ctx = build_context(_results(), tmp_path)
    assert ctx["bootstrap"] is not None
    assert ctx["bootstrap"][0]["name"] == "CL"


def test_context_bootstrap_none_when_absent(tmp_path):
    assert build_context(_results(), tmp_path)["bootstrap"] is None


# ---- render_markdown -----------------------------------------------------
def test_markdown_contains_fit_and_params(tmp_path):
    md = render_markdown(build_context(_results(), tmp_path))
    assert "ad3tr4_run" in md
    assert "123.45" in md          # OFV
    assert "CL" in md and "V" in md  # parameter names


def test_markdown_embeds_plots(tmp_path):
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    (diag / "dv_vs_pred.png").write_bytes(b"\x89PNG")
    md = render_markdown(build_context(_results(), tmp_path))
    assert "![dv_vs_pred]" in md


def test_markdown_omits_bootstrap_section_when_absent(tmp_path):
    md = render_markdown(build_context(_results(), tmp_path))
    assert "Bootstrap" not in md


def test_markdown_includes_bootstrap_section_when_present(tmp_path):
    bdir = tmp_path / "bootstrap"
    bdir.mkdir()
    pd.DataFrame([{"name": "CL", "original_est": 10.0, "boot_median": 10.2,
                   "ci_lo": 8.5, "ci_hi": 11.9, "n_success": 200}]).to_csv(
        bdir / "bootstrap_summary.csv", index=False)
    md = render_markdown(build_context(_results(), tmp_path))
    assert "Bootstrap" in md


# ---- render (file output) ------------------------------------------------
def test_render_writes_markdown(tmp_path):
    out = tmp_path / "out"
    path = render(_results(), tmp_path, out, fmt="md")
    assert path.exists() and path.suffix == ".md"
    assert "ad3tr4_run" in path.read_text()


@pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not installed")
def test_render_html_via_pandoc(tmp_path):
    path = render(_results(), tmp_path, tmp_path / "out", fmt="html")
    assert path.suffix == ".html"
    assert "<" in path.read_text()


@pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not installed")
def test_render_docx_via_pandoc(tmp_path):
    path = render(_results(), tmp_path, tmp_path / "out", fmt="docx")
    assert path.exists() and path.suffix == ".docx"
    assert path.stat().st_size > 0
