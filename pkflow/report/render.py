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


FORMATS = ("md", "html", "docx", "pdf")

# PDF engines pandoc can drive, in order of preference. wkhtmltopdf/weasyprint
# render the HTML path (good with embedded PNGs and no LaTeX needed); the
# LaTeX engines are the classic fallback.
_PDF_ENGINES = ("weasyprint", "wkhtmltopdf", "tectonic", "xelatex", "pdflatex")


def _find_pdf_engine() -> str | None:
    for eng in _PDF_ENGINES:
        if shutil.which(eng):
            return eng
    return None


def render(results: Results, run_dir: Path, out_dir: Path, fmt: str = "md") -> Path:
    """Write the report to out_dir in the chosen format and return its path.

    `md` writes Markdown directly; `html`/`docx`/`pdf` render Markdown then
    convert with pandoc. PDF additionally needs a PDF engine (weasyprint,
    wkhtmltopdf, or a LaTeX engine). Raises a clear error if a required tool
    is missing or the format is unknown.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_text = render_markdown(build_context(results, run_dir))
    md_path = out_dir / "report.md"
    md_path.write_text(md_text)
    if fmt == "md":
        return md_path

    if shutil.which("pandoc") is None:
        raise RuntimeError(
            f"pandoc is required to render {fmt!r} but was not found on PATH.\n"
            "  install it from https://pandoc.org/installing.html "
            "(e.g. `brew install pandoc`, `apt install pandoc`)."
        )

    out_path = out_dir / f"report.{fmt}"
    cmd = [
        "pandoc", str(md_path), "-o", str(out_path),
        # let pandoc resolve plot images whether the template used absolute or
        # run-dir-relative paths
        "--resource-path", f"{run_dir}:{out_dir}:{run_dir / 'diagnostics'}",
    ]

    if fmt == "pdf":
        engine = _find_pdf_engine()
        if engine is None:
            raise RuntimeError(
                "rendering PDF needs a PDF engine that pandoc can drive, but none "
                f"of {', '.join(_PDF_ENGINES)} were found on PATH.\n"
                "  easiest option: `pip install weasyprint` (or install wkhtmltopdf "
                "or a LaTeX distribution like TinyTeX/tectonic).\n"
                "  alternatively render `--format html` or `--format docx`."
            )
        cmd += [f"--pdf-engine={engine}"]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pandoc failed to render {fmt!r} (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return out_path
