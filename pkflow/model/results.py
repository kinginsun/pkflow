from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal
import pandas as pd
import yaml

Status = Literal["ok", "minimization_terminated", "boundary", "failed"]


def _py(value):
    """Coerce numpy scalars (e.g. np.float64 from pharmpy) to native Python
    types so yaml.safe_dump can serialize them. Leaves other values untouched."""
    if value is None:
        return None
    item = getattr(value, "item", None)  # numpy scalars expose .item()
    return item() if callable(item) else value


@dataclass
class Results:
    """Unified outcome of one model run. All backends collect() into this."""
    run_id: str
    backend: str
    model_path: Path
    started_at: datetime
    duration_s: float
    status: Status

    ofv: float | None = None
    aic: float | None = None
    bic: float | None = None
    condition_number: float | None = None

    parameters: pd.DataFrame = field(default_factory=pd.DataFrame)
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    etas: pd.DataFrame = field(default_factory=pd.DataFrame)
    covariates: pd.DataFrame = field(default_factory=pd.DataFrame)
    eta_shrinkage: dict[str, float] = field(default_factory=dict)
    eps_shrinkage: dict[str, float] = field(default_factory=dict)

    covariance_matrix: pd.DataFrame | None = None
    correlation_matrix: pd.DataFrame | None = None

    artifacts: dict[str, Path] = field(default_factory=dict)
    error_log: str = ""  # diagnostic text for status='failed' runs (e.g. tail of .lst)

    # ---- persistence ----
    def save(self, run_dir: Path) -> None:
        """Write results.yaml + parquet sidecars to a run directory."""
        run_dir.mkdir(parents=True, exist_ok=True)
        if not self.parameters.empty:
            self.parameters.to_parquet(run_dir / "parameters.parquet")
        if not self.predictions.empty:
            self.predictions.to_parquet(run_dir / "predictions.parquet")
        if not self.etas.empty:
            self.etas.to_parquet(run_dir / "etas.parquet")
        if not self.covariates.empty:
            self.covariates.to_parquet(run_dir / "covariates.parquet")

        meta = {
            "run_id": self.run_id,
            "backend": self.backend,
            "model_path": str(self.model_path),
            "started_at": self.started_at.isoformat(),
            "duration_s": self.duration_s,
            "status": self.status,
            "ofv": _py(self.ofv),
            "aic": _py(self.aic),
            "bic": _py(self.bic),
            "condition_number": _py(self.condition_number),
            "eta_shrinkage": {k: _py(v) for k, v in self.eta_shrinkage.items()},
            "eps_shrinkage": {k: _py(v) for k, v in self.eps_shrinkage.items()},
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "error_log": self.error_log,
        }
        (run_dir / "results.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))

    @classmethod
    def load(cls, run_dir: Path) -> "Results":
        meta = yaml.safe_load((run_dir / "results.yaml").read_text())
        r = cls(
            run_id=meta["run_id"],
            backend=meta["backend"],
            model_path=Path(meta["model_path"]),
            started_at=datetime.fromisoformat(meta["started_at"]),
            duration_s=meta["duration_s"],
            status=meta["status"],
            ofv=meta.get("ofv"),
            aic=meta.get("aic"),
            bic=meta.get("bic"),
            condition_number=meta.get("condition_number"),
            eta_shrinkage=meta.get("eta_shrinkage", {}),
            eps_shrinkage=meta.get("eps_shrinkage", {}),
            artifacts={k: Path(v) for k, v in meta.get("artifacts", {}).items()},
            error_log=meta.get("error_log", ""),
        )
        for attr, fname in [("parameters", "parameters.parquet"),
                            ("predictions", "predictions.parquet"),
                            ("etas", "etas.parquet"),
                            ("covariates", "covariates.parquet")]:
            p = run_dir / fname
            if p.exists():
                setattr(r, attr, pd.read_parquet(p))
        return r
