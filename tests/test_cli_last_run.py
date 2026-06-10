"""Tests for the last-run defaulting + run-dir validation in the CLI."""
from __future__ import annotations
from pathlib import Path
import pytest
from typer.testing import CliRunner

from pkflow.cli import app
from pkflow import state


runner = CliRunner()


def _make_valid_run(run_dir: Path) -> Path:
    """Minimal pkflow run dir (just enough for _resolve_run_dir to accept)."""
    run_dir.mkdir(parents=True)
    (run_dir / "results.yaml").write_text(
        "run_id: test\nbackend: nonmem\nmodel_path: m.ctl\n"
        "started_at: '2026-01-01T00:00:00'\nduration_s: 0.0\nstatus: ok\n"
    )
    return run_dir


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "user_cfg"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# happy path: marker exists, downstream commands default to it
# ---------------------------------------------------------------------------
def test_show_uses_last_run_when_omitted(isolated):
    run = _make_valid_run(isolated / "runs" / "m_20260101_000000")
    state.set_last_run(isolated / "runs", run)
    r = runner.invoke(app, ["show"])
    assert r.exit_code == 0
    assert "test" in r.output  # run_id from results.yaml
    assert "using last run" in r.output


def test_explicit_run_dir_overrides_last(isolated):
    last = _make_valid_run(isolated / "runs" / "m_old")
    state.set_last_run(isolated / "runs", last)
    explicit = _make_valid_run(isolated / "runs" / "m_explicit")
    r = runner.invoke(app, ["show", str(explicit)])
    assert r.exit_code == 0
    assert "using last run" not in r.output  # explicit suppresses the hint


# ---------------------------------------------------------------------------
# validation: missing / wrong / not-a-pkflow-run-dir
# ---------------------------------------------------------------------------
def test_omit_without_marker_errors(isolated):
    r = runner.invoke(app, ["show"])
    assert r.exit_code == 2
    assert "no previous successful run" in r.output


def test_nonexistent_path_errors(isolated):
    r = runner.invoke(app, ["show", str(isolated / "nope")])
    assert r.exit_code == 2
    assert "does not exist" in r.output


def test_path_is_a_file_errors(isolated):
    f = isolated / "a_file"
    f.write_text("x")
    r = runner.invoke(app, ["show", str(f)])
    assert r.exit_code == 2
    assert "not a directory" in r.output


def test_dir_without_results_yaml_errors(isolated):
    d = isolated / "bogus_run"
    d.mkdir()
    r = runner.invoke(app, ["show", str(d)])
    assert r.exit_code == 2
    assert "not a pkflow run directory" in r.output
    assert "pkflow collect" in r.output  # hints toward the fix


def test_stale_marker_points_to_deleted_dir(isolated):
    run = _make_valid_run(isolated / "runs" / "m")
    state.set_last_run(isolated / "runs", run)
    # delete the run dir — marker now stale
    import shutil
    shutil.rmtree(run)
    r = runner.invoke(app, ["show"])
    # state.get_last_run returns None when path missing → "no previous run" branch
    assert r.exit_code == 2
    assert "no previous successful run" in r.output


# ---------------------------------------------------------------------------
# collect is allowed on a dir without results.yaml (it CREATES it)
# ---------------------------------------------------------------------------
def test_collect_does_not_require_results_yaml(isolated):
    d = isolated / "raw_nonmem_dir"
    d.mkdir()
    # no .ctl / .mod either → collect should fail later with its own message,
    # but the run-dir validation must pass.
    r = runner.invoke(app, ["collect", str(d)])
    # exit non-zero but NOT for missing results.yaml — for missing ctl/mod
    assert "not a pkflow run directory" not in r.output


# ---------------------------------------------------------------------------
# state module unit tests
# ---------------------------------------------------------------------------
def test_set_and_get_last_run_roundtrip(tmp_path):
    runs = tmp_path / "runs"
    run = runs / "m_20260101_000000"
    run.mkdir(parents=True)
    state.set_last_run(runs, run)
    assert state.get_last_run(runs) == run.resolve()


def test_get_last_run_none_when_marker_missing(tmp_path):
    assert state.get_last_run(tmp_path / "runs") is None


def test_get_last_run_none_when_pointee_missing(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / state.LAST_RUN_FILE).write_text(str(tmp_path / "deleted"))
    assert state.get_last_run(runs) is None
