"""Persistent 'last successful run' marker.

After a successful `pkflow run`, the run directory is stamped into
`<runs_dir>/.last`. Downstream commands (show / diagnose / vpc / ...) use it
as the default when the user omits the run-dir argument.
"""
from __future__ import annotations
from pathlib import Path

LAST_RUN_FILE = ".last"


def last_run_marker(runs_dir: Path) -> Path:
    return runs_dir / LAST_RUN_FILE


def set_last_run(runs_dir: Path, run_dir: Path) -> None:
    """Record `run_dir` (absolute) as the most recent successful run."""
    marker = last_run_marker(runs_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(run_dir.resolve()))


def get_last_run(runs_dir: Path) -> Path | None:
    """Read the marker. Returns None if missing or stale (dir deleted)."""
    marker = last_run_marker(runs_dir)
    if not marker.exists():
        return None
    p = Path(marker.read_text().strip())
    return p if p.exists() else None
