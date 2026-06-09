from __future__ import annotations
from pyrana.executors import LocalExecutor


def test_runs_command_and_returns_zero(tmp_path):
    ex = LocalExecutor({})
    proc = ex.submit(["true"], cwd=tmp_path)
    assert ex.wait(proc) == 0


def test_nonzero_returncode_propagates(tmp_path):
    ex = LocalExecutor({})
    proc = ex.submit(["false"], cwd=tmp_path)
    assert ex.wait(proc) != 0


def test_stdout_captured_to_logfile(tmp_path):
    ex = LocalExecutor({})
    proc = ex.submit(["sh", "-c", "echo hello"], cwd=tmp_path)
    ex.wait(proc)
    assert (tmp_path / "stdout.log").read_text().strip() == "hello"
    assert (tmp_path / "stderr.log").exists()


def test_config_is_accessible():
    ex = LocalExecutor({"nmfe": "nmfe75"})
    assert ex.config["nmfe"] == "nmfe75"


def test_config_defaults_to_empty_dict():
    assert LocalExecutor().config == {}
