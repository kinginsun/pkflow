from __future__ import annotations
from pkflow import config


def test_load_returns_defaults_when_no_file(tmp_path):
    cfg = config.load(tmp_path / "does_not_exist.toml")
    assert cfg == config.DEFAULTS
    assert cfg["backend"] == "nonmem"
    assert cfg["executor"] == "local"
    assert cfg["nmfe"] == "nmfe75"
    assert cfg["runs_dir"] == "runs"


def test_load_overrides_from_toml(tmp_path):
    p = tmp_path / "pkflow.toml"
    p.write_text('backend = "stan"\nnmfe = "/opt/nm/nmfe74"\n')
    cfg = config.load(p)
    assert cfg["backend"] == "stan"
    assert cfg["nmfe"] == "/opt/nm/nmfe74"
    # unspecified keys keep defaults
    assert cfg["runs_dir"] == "runs"


def test_load_does_not_mutate_defaults(tmp_path):
    p = tmp_path / "pkflow.toml"
    p.write_text('backend = "mmdl"\n')
    config.load(p)
    assert config.DEFAULTS["backend"] == "nonmem"
