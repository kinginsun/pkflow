"""Run reports.

`build_context` (pure) assembles everything a report needs from a `Results`
plus its run dir; `render_markdown` fills a Jinja2 template; `render` writes
`report.md` and, for html/docx, converts it with system `pandoc`.

Markdown is the canonical render (no extra deps). HTML/DOCX need `pandoc` on
PATH — already standard on most analysis boxes.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..model import Results

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_context(results: Results, run_dir: Path) -> dict:
    """Assemble the template context: header, fit stats, parameter rows,
    shrinkage, any bootstrap summary, and existing diagnostic plots."""
    run_dir = Path(run_dir)

    params = []
    for _, row in results.parameters.iterrows():
        params.append({
            "name": row.get("name"),
            "type": row.get("type"),
            "estimate": row.get("estimate"),
            "se": row.get("se") if "se" in row else None,
            "rse_pct": row.get("rse_pct") if "rse_pct" in row else None,
        })

    # Existing diagnostic plots (png) under <run_dir>/diagnostics
    plots = []
    diag = run_dir / "diagnostics"
    if diag.is_dir():
        for png in sorted(diag.glob("*.png")):
            plots.append({"title": png.stem, "path": str(png)})

    # Bootstrap summary, if a bootstrap was run
    bootstrap = None
    boot_csv = run_dir / "bootstrap" / "bootstrap_summary.csv"
    if boot_csv.exists():
        bootstrap = pd.read_csv(boot_csv).to_dict(orient="records")

    return {
        "run_id": results.run_id,
        "backend": results.backend,
        "status": results.status,
        "model_path": str(results.model_path),
        "started_at": results.started_at.isoformat(),
        "duration_s": results.duration_s,
        "ofv": results.ofv,
        "aic": results.aic,
        "bic": results.bic,
        "condition_number": results.condition_number,
        "parameters": params,
        "eta_shrinkage": results.eta_shrinkage,
        "bootstrap": bootstrap,
        "plots": plots,
    }


def render_markdown(context: dict) -> str:
    """Render the Markdown report from a context dict."""
    return _env.get_template("run_report.md.j2").render(**context)


def render(results: Results, run_dir: Path, out_dir: Path, fmt: str = "md") -> Path:
    """Write the report to out_dir in the chosen format and return its path.

    `md` writes Markdown directly; `html`/`docx` render Markdown then convert
    with pandoc (raises if pandoc is missing or the format is unknown).
    """
    if fmt not in ("md", "html", "docx"):
        raise ValueError(f"unknown format {fmt!r}; choose md, html, or docx")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_text = render_markdown(build_context(results, run_dir))
    md_path = out_dir / "report.md"
    md_path.write_text(md_text)
    if fmt == "md":
        return md_path

    if shutil.which("pandoc") is None:
        raise RuntimeError(f"pandoc is required to render {fmt!r}; not found on PATH")
    out_path = out_dir / f"report.{fmt}"
    subprocess.run(
        ["pandoc", str(md_path), "-o", str(out_path)],
        check=True, capture_output=True,
    )
    return out_path
