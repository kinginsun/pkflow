"""Layered configuration for pkflow.

Resolution order (last wins):
    1. built-in DEFAULTS
    2. user-level config:    ~/.config/pkflow/config.toml
    3. project-level config: ./pkflow.toml  (cwd)
    4. explicit CLI flags    (handled by callers, not here)

The user-level file is where 'pkflow config set' writes by default — set
nmfe path once and reuse it across every project.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # 3.10 fallback

import tomli_w


DEFAULTS: dict = {
    "backend": "nonmem",
    "executor": "local",
    "nmfe": "nmfe75",
    "runs_dir": "runs",
}

# Keys that 'pkflow config set' will accept. Adding a new key here is the
# only place needed to extend the surface.
KNOWN_KEYS = frozenset(DEFAULTS)


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
def user_config_path() -> Path:
    """~/.config/pkflow/config.toml (honors XDG_CONFIG_HOME)."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "pkflow" / "config.toml"


def project_config_path(cwd: Path | None = None) -> Path:
    """./pkflow.toml (relative to cwd)."""
    return (cwd or Path.cwd()) / "pkflow.toml"


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------
def _read_toml(p: Path) -> dict:
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text())


def load(path: Path | None = None) -> dict:
    """Resolved config: DEFAULTS < user < project (< explicit `path` if given)."""
    cfg = dict(DEFAULTS)
    cfg.update(_read_toml(user_config_path()))
    cfg.update(_read_toml(project_config_path()))
    if path is not None:
        cfg.update(_read_toml(path))
    return cfg


def load_with_sources() -> dict[str, tuple]:
    """Like load(), but each value is (value, source) for `config show`.
    source ∈ {'default', 'user', 'project'}."""
    out = {k: (v, "default") for k, v in DEFAULTS.items()}
    for source, p in (("user", user_config_path()),
                      ("project", project_config_path())):
        for k, v in _read_toml(p).items():
            out[k] = (v, source)
    return out


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
def set_value(key: str, value, *, scope: str = "user") -> Path:
    """Set a config key in the user (default) or project file. Returns the path."""
    if key not in KNOWN_KEYS:
        raise KeyError(
            f"unknown key {key!r}. known: {sorted(KNOWN_KEYS)}"
        )
    if scope == "user":
        p = user_config_path()
    elif scope == "project":
        p = project_config_path()
    else:
        raise ValueError(f"scope must be 'user' or 'project', got {scope!r}")

    data = _read_toml(p)
    data[key] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tomli_w.dumps(data).encode())
    return p


def unset_value(key: str, *, scope: str = "user") -> Path:
    """Remove a key from the user or project file. Returns the path."""
    p = user_config_path() if scope == "user" else project_config_path()
    data = _read_toml(p)
    data.pop(key, None)
    if data:
        p.write_bytes(tomli_w.dumps(data).encode())
    elif p.exists():
        p.unlink()  # tidy: empty file → delete
    return p
