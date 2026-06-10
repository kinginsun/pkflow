from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
from typer.testing import CliRunner

import pkflow.cli as cli
from pkflow.model import Model
from .conftest import make_results

runner = CliRunner()


def _params(**kw):
    return pd.DataFrame([{"name": n, "type": "theta", "estimate": v}
                         for n, v in kw.items()])


class _FakeBackend:
    """parse() returns a Model whose raw exposes a dataset + id column, so the
    bootstrap orchestrator can run with no NONMEM."""
    name = "nonmem"

    def parse(self, path):
        raw = SimpleNamespace(
            dataset=pd.DataFrame({"ID": [1, 1, 2, 2, 3, 3],
                                  "TIME": [0, 1, 0, 1, 0, 1],
                                  "DV": [1, 2, 3, 4, 5, 6]}),
            datainfo=SimpleNamespace(id_column=SimpleNamespace(name="ID")),
        )
        return Model(path=Path(path), backend="nonmem", raw=raw)

    def run(self, model, run_dir, executor):
        run_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(run_dir=run_dir, returncode=0)

    _i = 0

    def collect(self, model, run_dir, handle):
        type(self)._i += 1
        return make_results(run_dir.name, parameters=_params(CL=10.0 + self._i * 0.1))


def test_bootstrap_command_runs_and_prints_summary(tmp_path, monkeypatch):
    ctl = tmp_path / "m.ctl"
    ctl.write_text("$PROBLEM x\n")
    monkeypatch.setattr(cli.config, "load",
                        lambda *a, **k: {"backend": "nonmem", "executor": "local",
                                          "nmfe": "nmfe76", "runs_dir": str(tmp_path / "runs")})
    monkeypatch.setattr(cli.backends, "get", lambda name: _FakeBackend())

    result = runner.invoke(cli.app, ["bootstrap", str(ctl), "--n", "4", "--seed", "1"])

    assert result.exit_code == 0, result.output
    assert "converged: 4/4" in result.output
    assert "CL" in result.output
    # summary csv persisted under the run dir
    summaries = list((tmp_path / "runs").glob("*/bootstrap/bootstrap_summary.csv"))
    assert len(summaries) == 1
