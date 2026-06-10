from __future__ import annotations
from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # 3.10 fallback


DEFAULTS = {
    "backend": "nonmem",
    "executor": "local",
    "nmfe": "nmfe75",
    "runs_dir": "runs",
}


def load(path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    p = path or Path("pkflow.toml")
    if p.exists():
        cfg.update(tomllib.loads(p.read_text()))
    return cfg
