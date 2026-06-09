from __future__ import annotations
from pathlib import Path
import tomllib


DEFAULTS = {
    "backend": "nonmem",
    "executor": "local",
    "nmfe": "nmfe75",
    "runs_dir": "runs",
}


def load(path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    p = path or Path("pyrana.toml")
    if p.exists():
        cfg.update(tomllib.loads(p.read_text()))
    return cfg
