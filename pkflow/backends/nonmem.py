"""NONMEM backend — thin wrapper around pharmpy for parse + collect.

The actual NONMEM binary invocation is delegated to the Executor; this module
only knows how to (1) read a .ctl file into a Model, (2) build the command line,
and (3) read .lst/.ext back into a Results.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import re
import shutil
import time
import pandas as pd

from ..model import Model, Results
from .base import RunHandle


class NonmemBackend:
    name = "nonmem"

    # ---- parse ------------------------------------------------------------
    def parse(self, path: Path) -> Model:
        import pharmpy.modeling as pm
        raw = pm.read_model(path)
        return Model(
            path=Path(path),
            backend="nonmem",
            dataset=Path(raw.datainfo.path) if raw.datainfo.path else None,
            name=raw.name,
            raw=raw,
        )

    # ---- run --------------------------------------------------------------
    def run(self, model: Model, run_dir: Path, executor) -> RunHandle:
        run_dir.mkdir(parents=True, exist_ok=True)
        ctl_copy = run_dir / model.path.name
        ctl_text = model.path.read_text()

        # Make the run dir self-contained: copy the dataset alongside the ctl
        # and rewrite $DATA to reference it by bare name, so a relative
        # `$DATA ../d/foo.csv` still resolves when NONMEM runs in run_dir.
        if model.dataset is not None and Path(model.dataset).exists():
            data_dest = run_dir / Path(model.dataset).name
            shutil.copy(model.dataset, data_dest)
            ctl_text = _localize_data_record(ctl_text, data_dest.name)

        ctl_copy.write_text(ctl_text)

        # NONMEM convention: `nmfe75 model.ctl model.lst`
        nmfe = executor.config.get("nmfe", "nmfe75")
        lst = ctl_copy.with_suffix(".lst")
        cmd = [nmfe, ctl_copy.name, lst.name]

        proc = executor.submit(cmd, cwd=run_dir)
        rc = executor.wait(proc)
        return RunHandle(run_dir=run_dir, returncode=rc, lst=lst)

    # ---- collect ----------------------------------------------------------
    def collect(self, model: Model, run_dir: Path, handle: RunHandle) -> Results:
        import pharmpy.modeling as pm
        from pharmpy.tools import read_modelfit_results

        started = datetime.fromtimestamp(handle.run_dir.stat().st_mtime)
        ctl = run_dir / model.path.name
        mfr = read_modelfit_results(ctl)

        # Parameters → unified DataFrame
        params_df = self._params_to_df(mfr)

        # Predictions: try $TABLE outputs
        preds = self._read_predictions(run_dir)

        # Etas + shrinkage
        etas = getattr(mfr, "individual_estimates", pd.DataFrame())
        if not isinstance(etas, pd.DataFrame):
            etas = pd.DataFrame()
        eta_shr = self._eta_shrinkage(model, mfr, etas)
        covariates = self._extract_covariates(model)

        status: str = "ok"
        if handle.returncode and handle.returncode != 0:
            status = "failed"
        elif getattr(mfr, "minimization_successful", True) is False:
            status = "minimization_terminated"

        return Results(
            run_id=run_dir.name,
            backend="nonmem",
            model_path=model.path,
            started_at=started,
            duration_s=0.0,  # executor should stamp; placeholder
            status=status,
            ofv=getattr(mfr, "ofv", None),
            aic=self._safe_ic(mfr, "aic"),
            bic=self._safe_ic(mfr, "bic"),
            condition_number=getattr(mfr, "condition_number", None),
            parameters=params_df,
            predictions=preds,
            etas=etas if isinstance(etas, pd.DataFrame) else pd.DataFrame(),
            eta_shrinkage=eta_shr,
            covariates=covariates,
            artifacts={
                "lst": handle.extra.get("lst", ctl.with_suffix(".lst")),
                "ext": ctl.with_suffix(".ext"),
                "phi": ctl.with_suffix(".phi"),
                "cov": ctl.with_suffix(".cov"),
            },
        )

    # ---- simulate ---------------------------------------------------------
    def simulate(
        self,
        model: Model,
        results: Results,
        run_dir: Path,
        executor,
        n_sim: int = 500,
        seed: int = 1234,
    ) -> pd.DataFrame:
        """Convert estimation model → simulation, run, collect DV per replicate.

        Strategy: use pharmpy to rewrite $ESTIMATION as $SIMULATION with N
        subproblems, fix parameters at the final estimates, then run nmfe75 and
        read the resulting $TABLE. Subproblem index becomes REPLICATE.
        """
        import pharmpy.modeling as pm

        sim_dir = run_dir / "vpc_sim"
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Build simulation model from the fitted one ($ESTIMATION → $SIMULATION
        # with N subproblems) and write its control stream.
        sim_model = pm.set_simulation(model.raw, n=n_sim, seed=seed)
        sim_ctl = sim_dir / f"{model.stem}_sim.ctl"
        pm.write_model(sim_model, sim_ctl, force=True)

        # Make the sim dir self-contained: copy the dataset in and point $DATA
        # at it by basename (pharmpy writes $DATA as a path relative to cwd).
        if model.dataset is not None and Path(model.dataset).exists():
            data_dest = sim_dir / Path(model.dataset).name
            shutil.copy(model.dataset, data_dest)
            sim_ctl.write_text(_localize_data_record(sim_ctl.read_text(), data_dest.name))

        nmfe = executor.config.get("nmfe", "nmfe75")
        lst = sim_ctl.with_suffix(".lst")
        proc = executor.submit([nmfe, sim_ctl.name, lst.name], cwd=sim_dir)
        rc = executor.wait(proc)
        if rc != 0:
            raise RuntimeError(f"simulation nmfe exited {rc}; see {sim_dir}/stderr.log")

        # NONMEM with N subproblems stacks one $TABLE per replicate, each
        # prefixed by a "TABLE NO." header. Read it directly (read_modelfit_
        # results does not surface simulation tables).
        tab = _find_simulation_table(sim_dir, sim_ctl)
        if tab is None:
            raise RuntimeError(f"simulation produced no readable $TABLE in {sim_dir}")
        sim_df = _read_stacked_table(tab)

        missing = {"ID", "TIME", "DV"} - set(sim_df.columns)
        if missing:
            raise RuntimeError(f"simulation table missing columns {sorted(missing)}")
        return sim_df[["REPLICATE", "ID", "TIME", "DV"]].copy()

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _params_to_df(mfr) -> pd.DataFrame:
        est = getattr(mfr, "parameter_estimates", None)
        se = getattr(mfr, "standard_errors", None)
        if est is None:
            return pd.DataFrame()
        rows = []
        for name, val in est.items():
            s = float(se[name]) if se is not None and name in se else None
            rows.append({
                "name": name,
                "type": _classify(name),
                "estimate": float(val),
                "se": s,
                "rse_pct": (abs(s / val) * 100 if s and val else None),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def _read_predictions(run_dir: Path) -> pd.DataFrame:
        # Look for any sdtab/patab-like $TABLE outputs
        for fname in ("sdtab", "sdtab1", "patab", "tab"):
            p = run_dir / fname
            if p.exists():
                try:
                    return pd.read_csv(p, sep=r"\s+", skiprows=1)
                except Exception:
                    pass
        return pd.DataFrame()

    @staticmethod
    def _extract_covariates(model) -> pd.DataFrame:
        """Per-subject covariates from the model's dataset via pharmpy datainfo.

        Prefers columns typed 'covariate'; otherwise constant-per-subject
        user columns (type 'unknown'). Degrades to empty on any failure."""
        if model.raw is None or not hasattr(model.raw, "dataset"):
            return pd.DataFrame()
        try:
            di = model.raw.datainfo
            ds = model.raw.dataset
            id_col = di.id_column.name
            typed = [c.name for c in di if c.type == "covariate"]
            candidates = [c.name for c in di
                          if c.type == "unknown" and c.name != id_col]
            return _select_covariates(ds, id_col, typed, candidates)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _eta_shrinkage(model, mfr, etas) -> dict[str, float]:
        """η shrinkage via pharmpy (no `individual_shrinkage` attr in 2.x).

        Needs the raw model + parameter estimates + individual η estimates;
        degrades to {} if any are unavailable (e.g. no covariance step)."""
        if model.raw is None or etas.empty:
            return {}
        try:
            import pharmpy.modeling as pm
            s = pm.calculate_eta_shrinkage(model.raw, mfr.parameter_estimates, etas)
            return {k: float(v) for k, v in s.to_dict().items()}
        except Exception:
            return {}

    @staticmethod
    def _safe_ic(mfr, attr: str):
        try:
            v = getattr(mfr, attr, None)
            return float(v) if v is not None else None
        except Exception:
            return None


def _select_covariates(ds, id_col: str, typed_cov, candidates) -> pd.DataFrame:
    """Per-subject covariate table (pure).

    Uses pharmpy-typed covariate columns when present; otherwise falls back to
    `candidates` that are constant within each subject (true time-constant
    covariates). Returns one row per subject (id + covariate columns), or an
    empty frame if nothing qualifies."""
    if typed_cov:
        cols = list(typed_cov)
    else:
        cols = [c for c in candidates
                if ds.groupby(id_col)[c].nunique().max() == 1     # constant per subject
                and ds.groupby(id_col)[c].first().nunique() > 1]  # varies across subjects
    if not cols:
        return pd.DataFrame()
    return ds.groupby(id_col, as_index=False)[cols].first()


def _find_simulation_table(sim_dir: Path, sim_ctl: Path):
    """Locate the $TABLE output file: prefer the FILE= named in the control,
    else any file in the dir that begins with a 'TABLE NO.' header."""
    m = re.search(r"\$TABLE.*?FILE\s*=\s*(\S+)", sim_ctl.read_text(), re.S | re.I)
    if m:
        cand = sim_dir / m.group(1)
        if cand.exists():
            return cand
    for p in sorted(sim_dir.iterdir()):
        if p.is_file():
            try:
                if p.open().readline().startswith("TABLE NO"):
                    return p
            except (OSError, UnicodeDecodeError):
                continue
    return None


def _read_stacked_table(path: Path) -> pd.DataFrame:
    """Parse a NONMEM simulation $TABLE (N subproblems stacked, each led by a
    'TABLE NO.' line then a header) into one frame with a REPLICATE column."""
    rows, header, rep = [], None, 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("TABLE NO"):
                rep += 1
                header = None
            elif header is None:
                header = line.split()
            else:
                rows.append([rep] + line.split())
    df = pd.DataFrame(rows, columns=["REPLICATE"] + (header or []))
    return df.apply(pd.to_numeric, errors="coerce")


def _localize_data_record(ctl_text: str, data_name: str) -> str:
    """Rewrite the first `$DATA <path>` token to a bare basename, so a copied
    control file references a dataset sitting next to it in the run dir.
    Leaves the record's options (IGNORE=, etc.) untouched."""
    return re.sub(
        r"(?im)^(\s*\$DATA\s+)(\S+)",
        lambda m: m.group(1) + data_name,
        ctl_text,
        count=1,
    )


def _classify(name: str) -> str:
    n = name.upper()
    if "OMEGA" in n: return "omega"
    if "SIGMA" in n: return "sigma"
    return "theta"
