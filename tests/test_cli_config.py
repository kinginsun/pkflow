from __future__ import annotations
import pytest
from typer.testing import CliRunner

from pkflow.cli import app


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    user = tmp_path / "user"
    project = tmp_path / "project"
    user.mkdir()
    project.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user))
    monkeypatch.chdir(project)
    return CliRunner(), user, project


def test_show_displays_defaults(isolated):
    runner, _, _ = isolated
    r = runner.invoke(app, ["config", "show"])
    assert r.exit_code == 0
    assert "backend" in r.output
    assert "nonmem" in r.output
    assert "default" in r.output


def test_set_persists_and_show_reflects(isolated):
    runner, user, _ = isolated
    r = runner.invoke(app, ["config", "set", "nmfe", "/opt/nm760/run/nmfe76"])
    assert r.exit_code == 0
    assert (user / "pkflow" / "config.toml").exists()

    r = runner.invoke(app, ["config", "get", "nmfe"])
    assert r.exit_code == 0
    assert "/opt/nm760/run/nmfe76" in r.output


def test_set_project_scope_writes_cwd(isolated):
    runner, _, project = isolated
    r = runner.invoke(app, ["config", "set", "--project", "backend", "stan"])
    assert r.exit_code == 0
    assert (project / "pkflow.toml").exists()
    assert (project / "pkflow.toml").read_text().strip().startswith("backend")


def test_set_rejects_unknown_key(isolated):
    runner, _, _ = isolated
    r = runner.invoke(app, ["config", "set", "wat", "x"])
    assert r.exit_code == 1
    assert "unknown key" in r.output


def test_get_unknown_key_exits_nonzero(isolated):
    runner, _, _ = isolated
    r = runner.invoke(app, ["config", "get", "totally_made_up"])
    assert r.exit_code == 1


def test_unset_restores_default(isolated):
    runner, _, _ = isolated
    runner.invoke(app, ["config", "set", "nmfe", "/x"])
    r = runner.invoke(app, ["config", "unset", "nmfe"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["config", "get", "nmfe"])
    assert "nmfe75" in r.output


def test_path_prints_user_file(isolated):
    runner, user, _ = isolated
    r = runner.invoke(app, ["config", "path"])
    assert r.exit_code == 0
    assert str(user / "pkflow" / "config.toml") in r.output


def test_path_project_flag(isolated):
    runner, _, project = isolated
    r = runner.invoke(app, ["config", "path", "--project"])
    assert r.exit_code == 0
    assert str(project / "pkflow.toml") in r.output
