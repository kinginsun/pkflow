from __future__ import annotations
from pathlib import Path
import pytest

from pkflow import config


# ---------------------------------------------------------------------------
# fixtures: redirect user + project config to tmp_path so we never touch $HOME
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"
    user_dir.mkdir()
    project_dir.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_dir))
    monkeypatch.chdir(project_dir)
    return user_dir, project_dir


# ---------------------------------------------------------------------------
# load layering
# ---------------------------------------------------------------------------
def test_load_returns_defaults_when_no_file(isolated_config):
    cfg = config.load()
    assert cfg == config.DEFAULTS


def test_load_overrides_from_explicit_toml(tmp_path):
    p = tmp_path / "pkflow.toml"
    p.write_text('backend = "stan"\nnmfe = "/opt/nm/nmfe74"\n')
    cfg = config.load(p)
    assert cfg["backend"] == "stan"
    assert cfg["nmfe"] == "/opt/nm/nmfe74"
    assert cfg["runs_dir"] == "runs"  # untouched key keeps default


def test_load_project_overrides_user(isolated_config):
    user, project = isolated_config
    (user / "pkflow" / "config.toml").parent.mkdir(parents=True)
    (user / "pkflow" / "config.toml").write_text('nmfe = "/opt/u/nmfe75"\n')
    (project / "pkflow.toml").write_text('nmfe = "/opt/p/nmfe75"\n')
    cfg = config.load()
    assert cfg["nmfe"] == "/opt/p/nmfe75"


def test_load_user_overrides_default(isolated_config):
    user, _ = isolated_config
    (user / "pkflow" / "config.toml").parent.mkdir(parents=True)
    (user / "pkflow" / "config.toml").write_text('nmfe = "/opt/nm/nmfe76"\n')
    cfg = config.load()
    assert cfg["nmfe"] == "/opt/nm/nmfe76"


def test_load_does_not_mutate_defaults(isolated_config):
    user, _ = isolated_config
    (user / "pkflow" / "config.toml").parent.mkdir(parents=True)
    (user / "pkflow" / "config.toml").write_text('backend = "mmdl"\n')
    config.load()
    assert config.DEFAULTS["backend"] == "nonmem"


# ---------------------------------------------------------------------------
# load_with_sources
# ---------------------------------------------------------------------------
def test_load_with_sources_marks_origin(isolated_config):
    user, project = isolated_config
    (user / "pkflow" / "config.toml").parent.mkdir(parents=True)
    (user / "pkflow" / "config.toml").write_text('nmfe = "/u/nmfe"\n')
    (project / "pkflow.toml").write_text('runs_dir = "outputs"\n')
    rows = config.load_with_sources()
    assert rows["backend"] == ("nonmem", "default")
    assert rows["nmfe"] == ("/u/nmfe", "user")
    assert rows["runs_dir"] == ("outputs", "project")


# ---------------------------------------------------------------------------
# set / unset
# ---------------------------------------------------------------------------
def test_set_value_writes_user_file(isolated_config):
    user, _ = isolated_config
    path = config.set_value("nmfe", "/opt/nm760/run/nmfe76", scope="user")
    assert path == user / "pkflow" / "config.toml"
    assert path.exists()
    assert config.load()["nmfe"] == "/opt/nm760/run/nmfe76"


def test_set_value_writes_project_file(isolated_config):
    _, project = isolated_config
    path = config.set_value("backend", "stan", scope="project")
    assert path == project / "pkflow.toml"
    assert config.load()["backend"] == "stan"


def test_set_value_rejects_unknown_key(isolated_config):
    with pytest.raises(KeyError, match="unknown key"):
        config.set_value("totally_made_up", "x")


def test_set_value_rejects_unknown_scope(isolated_config):
    with pytest.raises(ValueError, match="scope must be"):
        config.set_value("nmfe", "/x", scope="global")


def test_unset_removes_key(isolated_config):
    config.set_value("nmfe", "/x", scope="user")
    config.set_value("backend", "stan", scope="user")
    config.unset_value("nmfe", scope="user")
    cfg = config.load()
    assert cfg["nmfe"] == "nmfe75"     # back to default
    assert cfg["backend"] == "stan"    # other key preserved


def test_unset_deletes_empty_file(isolated_config):
    config.set_value("nmfe", "/x", scope="user")
    config.unset_value("nmfe", scope="user")
    assert not config.user_config_path().exists()
