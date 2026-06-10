from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest

from pkflow.backends.nonmem import NonmemBackend, _classify, _select_covariates
from pkflow.model import Model, Results

TEMPLATE = Path("/home/ubuntu/pirana/templates/004.mod")


# ---- parse (real pharmpy) ------------------------------------------------
def test_parse_reads_template():
    m = NonmemBackend().parse(TEMPLATE)
    assert m.backend == "nonmem"
    assert m.stem == "004"
    assert m.raw is not None
    assert m.dataset is not None and m.dataset.name == "nm_001.csv"


# ---- pure helpers --------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("THETA(1)", "theta"),
    ("OMEGA(1,1)", "omega"),
    ("SIGMA(1,1)", "sigma"),
    ("CL", "theta"),
])
def test_classify(name, expected):
    assert _classify(name) == expected


def test_params_to_df_builds_rows_with_rse():
    est = pd.Series({"THETA(1)": 10.0, "OMEGA(1,1)": 0.1})
    se = pd.Series({"THETA(1)": 1.0, "OMEGA(1,1)": 0.02})
    mfr = SimpleNamespace(parameter_estimates=est, standard_errors=se)
    df = NonmemBackend._params_to_df(mfr)
    row = df.set_index("name").loc["THETA(1)"]
    assert row["estimate"] == 10.0
    assert row["se"] == 1.0
    assert row["rse_pct"] == pytest.approx(10.0)
    assert row["type"] == "theta"


def test_params_to_df_empty_when_no_estimates():
    mfr = SimpleNamespace(parameter_estimates=None)
    assert NonmemBackend._params_to_df(mfr).empty


def test_safe_ic_returns_none_on_missing():
    assert NonmemBackend._safe_ic(SimpleNamespace(), "aic") is None


def test_safe_ic_casts_to_float():
    assert NonmemBackend._safe_ic(SimpleNamespace(aic=123), "aic") == 123.0


def test_read_predictions_empty_when_no_table(tmp_path):
    assert NonmemBackend._read_predictions(tmp_path).empty


def test_read_predictions_reads_sdtab(tmp_path):
    (tmp_path / "sdtab").write_text("TABLE\n DV PRED\n 1.0 1.1\n 2.0 2.2\n")
    df = NonmemBackend._read_predictions(tmp_path)
    assert list(df.columns) == ["DV", "PRED"]
    assert len(df) == 2


# ---- covariate selection (pure) ------------------------------------------
def _cov_dataset():
    # WT/SEX constant per subject (true covariates); CONC time-varying
    return pd.DataFrame({
        "ID":   [1, 1, 2, 2],
        "TIME": [0, 1, 0, 1],
        "WT":   [70, 70, 85, 85],
        "SEX":  [0, 0, 1, 1],
        "CONC": [5.0, 3.0, 6.0, 4.0],
    })


def test_select_covariates_prefers_typed():
    out = _select_covariates(_cov_dataset(), "ID", typed_cov=["WT"], candidates=["SEX", "CONC"])
    assert list(out.columns) == ["ID", "WT"]
    assert out.set_index("ID")["WT"].to_dict() == {1: 70, 2: 85}


def test_select_covariates_falls_back_to_constant_columns():
    # no typed covariates → keep constant-per-subject candidates, drop CONC
    out = _select_covariates(_cov_dataset(), "ID", typed_cov=[], candidates=["WT", "SEX", "CONC"])
    assert "WT" in out.columns and "SEX" in out.columns
    assert "CONC" not in out.columns
    assert len(out) == 2  # one row per subject


def test_select_covariates_drops_population_constant():
    # WT is constant for everyone (no between-subject variation) → not a useful
    # covariate; SEX varies across subjects → kept
    ds = pd.DataFrame({
        "ID":  [1, 1, 2, 2, 3, 3],
        "WT":  [70, 70, 70, 70, 70, 70],
        "SEX": [0, 0, 1, 1, 0, 0],
    })
    out = _select_covariates(ds, "ID", typed_cov=[], candidates=["WT", "SEX"])
    assert "SEX" in out.columns
    assert "WT" not in out.columns


def test_select_covariates_empty_when_nothing_qualifies():
    out = _select_covariates(_cov_dataset(), "ID", typed_cov=[], candidates=["CONC"])
    assert out.empty


def test_collect_stores_covariates(tmp_path, monkeypatch):
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: _fake_mfr())
    covs = pd.DataFrame({"ID": [1, 2], "WT": [70, 85]})
    monkeypatch.setattr(NonmemBackend, "_extract_covariates",
                        staticmethod(lambda model: covs))
    r = NonmemBackend().collect(Model(path=Path("m.ctl"), backend="nonmem"),
                                tmp_path, RunHandle(run_dir=tmp_path, returncode=0))
    pd.testing.assert_frame_equal(r.covariates, covs)


# ---- run (fake executor) -------------------------------------------------
class FakeExecutor:
    def __init__(self, config, rc=0):
        self.config = config
        self.rc = rc
        self.cmd = None
        self.cwd = None

    def submit(self, cmd, cwd):
        self.cmd, self.cwd = cmd, cwd
        return "proc"

    def wait(self, proc):
        return self.rc


def test_run_copies_ctl_and_builds_command(tmp_path):
    ctl = tmp_path / "m.ctl"
    ctl.write_text("$PROBLEM x\n")
    model = Model(path=ctl, backend="nonmem")
    run_dir = tmp_path / "run"
    ex = FakeExecutor({"nmfe": "nmfe76"})

    handle = NonmemBackend().run(model, run_dir, ex)

    assert (run_dir / "m.ctl").exists()           # ctl copied in
    assert ex.cmd == ["nmfe76", "m.ctl", "m.lst"]  # nmfe convention
    assert handle.returncode == 0
    assert handle.extra["lst"].name == "m.lst"


def test_run_copies_dataset_into_run_dir(tmp_path):
    # model dir with a relative $DATA reference
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.csv").write_text("ID,TIME,DV\n1,0,1\n")
    ctl = src / "m.ctl"
    ctl.write_text("$PROBLEM x\n$DATA data.csv IGNORE=@\n")
    model = Model(path=ctl, backend="nonmem", dataset=src / "data.csv")

    run_dir = tmp_path / "run"
    NonmemBackend().run(model, run_dir, FakeExecutor({"nmfe": "nmfe76"}))

    assert (run_dir / "data.csv").exists()             # dataset copied in
    assert (run_dir / "data.csv").read_text() == "ID,TIME,DV\n1,0,1\n"


def test_run_rewrites_data_record_to_basename(tmp_path):
    # $DATA points up a directory; run dir must reference it by bare name
    src = tmp_path / "models"
    data = tmp_path / "shared"
    src.mkdir(); data.mkdir()
    (data / "pk.csv").write_text("ID\n1\n")
    ctl = src / "m.ctl"
    ctl.write_text("$PROBLEM x\n$DATA ../shared/pk.csv IGNORE=C\n")
    model = Model(path=ctl, backend="nonmem", dataset=data / "pk.csv")

    run_dir = tmp_path / "run"
    NonmemBackend().run(model, run_dir, FakeExecutor({}))

    copied_ctl = (run_dir / "m.ctl").read_text()
    assert "$DATA pk.csv IGNORE=C" in copied_ctl
    assert "../shared" not in copied_ctl
    assert (run_dir / "pk.csv").exists()


def test_run_without_dataset_still_works(tmp_path):
    # dataset=None (e.g. unparsed model) → no copy, ctl written verbatim
    ctl = tmp_path / "m.ctl"
    ctl.write_text("$PROBLEM x\n")
    run_dir = tmp_path / "run"
    NonmemBackend().run(Model(path=ctl, backend="nonmem"), run_dir, FakeExecutor({}))
    assert (run_dir / "m.ctl").read_text() == "$PROBLEM x\n"


def test_run_propagates_failure_returncode(tmp_path):
    ctl = tmp_path / "m.ctl"
    ctl.write_text("$PROBLEM x\n")
    run_dir = tmp_path / "run"
    handle = NonmemBackend().run(
        Model(path=ctl, backend="nonmem"), run_dir, FakeExecutor({}, rc=1)
    )
    assert handle.returncode == 1


# ---- collect (stubbed pharmpy boundary) ----------------------------------
def _fake_mfr():
    # mirrors pharmpy 2.x: no `individual_shrinkage` attribute — shrinkage is
    # computed via pm.calculate_eta_shrinkage, not read off the results object.
    return SimpleNamespace(
        parameter_estimates=pd.Series({"THETA(1)": 5.0}),
        standard_errors=pd.Series({"THETA(1)": 0.5}),
        ofv=999.0,
        condition_number=20.0,
        individual_estimates=pd.DataFrame({"ETA_1": [0.1, -0.1]}),
        minimization_successful=True,
        aic=1009.0,
        bic=1019.0,
    )


def test_collect_maps_mfr_to_results(tmp_path, monkeypatch):
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: _fake_mfr())

    model = Model(path=Path("m.ctl"), backend="nonmem")
    handle = RunHandle(run_dir=tmp_path, returncode=0, lst=tmp_path / "m.lst")
    r = NonmemBackend().collect(model, tmp_path, handle)

    assert isinstance(r, Results)
    assert r.ofv == 999.0
    assert r.condition_number == 20.0
    assert r.status == "ok"
    assert len(r.parameters) == 1


def test_collect_computes_eta_shrinkage_via_pharmpy(tmp_path, monkeypatch):
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    import pharmpy.modeling as pm
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: _fake_mfr())
    # pharmpy computes shrinkage from model + estimates + individual estimates
    monkeypatch.setattr(pm, "calculate_eta_shrinkage",
                        lambda model, est, ie, **k: pd.Series({"ETA_1": 0.42}),
                        raising=False)

    model = Model(path=Path("m.ctl"), backend="nonmem", raw=object())
    r = NonmemBackend().collect(model, tmp_path,
                                RunHandle(run_dir=tmp_path, returncode=0))
    assert r.eta_shrinkage == {"ETA_1": 0.42}
    assert list(r.etas.columns) == ["ETA_1"]


def test_collect_shrinkage_empty_when_uncomputable(tmp_path, monkeypatch):
    # no raw model / pharmpy raises → shrinkage degrades to {} (no crash)
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: _fake_mfr())
    r = NonmemBackend().collect(Model(path=Path("m.ctl"), backend="nonmem"),
                                tmp_path, RunHandle(run_dir=tmp_path, returncode=0))
    assert r.eta_shrinkage == {}


def test_collect_flags_failed_on_nonzero_returncode(tmp_path, monkeypatch):
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: _fake_mfr())
    r = NonmemBackend().collect(
        Model(path=Path("m.ctl"), backend="nonmem"),
        tmp_path,
        RunHandle(run_dir=tmp_path, returncode=1),
    )
    assert r.status == "failed"


def test_collect_flags_minimization_terminated(tmp_path, monkeypatch):
    from pkflow.backends.base import RunHandle
    import pharmpy.tools
    mfr = _fake_mfr()
    mfr.minimization_successful = False
    monkeypatch.setattr(pharmpy.tools, "read_modelfit_results", lambda ctl: mfr)
    r = NonmemBackend().collect(
        Model(path=Path("m.ctl"), backend="nonmem"),
        tmp_path,
        RunHandle(run_dir=tmp_path, returncode=0),
    )
    assert r.status == "minimization_terminated"


def _sim_results():
    return Results(run_id="r", backend="nonmem", model_path=Path("m.ctl"),
                   started_at=__import__("datetime").datetime(2026, 6, 9),
                   duration_s=0.0, status="ok")


# stacked simulation $TABLE: 2 subproblems, each with a TABLE NO. header
_STACKED = (
    "TABLE NO.  1\n ID TIME DV\n 1 0.0 1.0\n 2 0.0 2.0\n"
    "TABLE NO.  2\n ID TIME DV\n 1 0.0 1.1\n 2 0.0 2.1\n"
)


# ---- simulate (stubbed pharmpy write + fake executor) --------------------
def test_simulate_reads_stacked_table_into_replicates(tmp_path, monkeypatch):
    import pharmpy.modeling as pm

    def fake_write_model(model, path, force=True):
        # pharmpy writes the sim control; NONMEM (faked) emits the stacked table
        Path(path).write_text("$PROBLEM x\n$TABLE ID TIME DV FILE=sdtab1\n"
                              "$SIMULATION (1) SUBPROBLEMS=2 ONLYSIMULATION\n")
        (Path(path).parent / "sdtab1").write_text(_STACKED)

    monkeypatch.setattr(pm, "set_simulation", lambda m, n, seed: object(), raising=False)
    monkeypatch.setattr(pm, "write_model", fake_write_model, raising=False)

    model = Model(path=Path("m.ctl"), backend="nonmem", raw=object())
    out = NonmemBackend().simulate(model, _sim_results(), tmp_path,
                                   FakeExecutor({"nmfe": "nmfe76"}), n_sim=2)
    assert list(out.columns) == ["REPLICATE", "ID", "TIME", "DV"]
    assert set(out["REPLICATE"]) == {1, 2}
    assert len(out) == 4


def test_simulate_raises_on_nonzero_returncode(tmp_path, monkeypatch):
    import pharmpy.modeling as pm
    monkeypatch.setattr(pm, "set_simulation", lambda m, n, seed: object(), raising=False)
    monkeypatch.setattr(pm, "write_model", lambda model, path, force=True: None, raising=False)

    model = Model(path=Path("m.ctl"), backend="nonmem", raw=object())
    with pytest.raises(RuntimeError, match="nmfe exited"):
        NonmemBackend().simulate(model, _sim_results(), tmp_path,
                                 FakeExecutor({}, rc=1), n_sim=2)


def test_read_stacked_table_assigns_replicate_per_block(tmp_path):
    from pkflow.backends.nonmem import _read_stacked_table
    p = tmp_path / "sdtab1"
    p.write_text(_STACKED)
    df = _read_stacked_table(p)
    assert df["REPLICATE"].tolist() == [1, 1, 2, 2]
    assert df.loc[df["REPLICATE"] == 2, "DV"].tolist() == [1.1, 2.1]
