from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest

from pkflow.model import Results


def make_results(
    run_id: str,
    *,
    ofv: float | None = None,
    status: str = "ok",
    n_params: int = 0,
    aic: float | None = None,
    bic: float | None = None,
    condition_number: float | None = None,
    predictions: pd.DataFrame | None = None,
    parameters: pd.DataFrame | None = None,
    eta_shrinkage: dict | None = None,
    eps_shrinkage: dict | None = None,
    etas: pd.DataFrame | None = None,
    covariates: pd.DataFrame | None = None,
) -> Results:
    """Build a minimal Results object for tests, no NONMEM run required.

    Pass `parameters` to supply an explicit estimates table; otherwise
    `n_params` synthesises THETA1..N with estimate=index.
    """
    if parameters is not None:
        params = parameters
    else:
        params = pd.DataFrame(
            [{"name": f"THETA{i + 1}", "type": "theta", "estimate": float(i)}
             for i in range(n_params)]
        )
    return Results(
        run_id=run_id,
        backend="nonmem",
        model_path=Path(f"{run_id}.ctl"),
        started_at=datetime(2026, 6, 9, 12, 0, 0),
        duration_s=1.0,
        status=status,
        ofv=ofv,
        aic=aic,
        bic=bic,
        condition_number=condition_number,
        parameters=params,
        predictions=predictions if predictions is not None else pd.DataFrame(),
        eta_shrinkage=eta_shrinkage or {},
        eps_shrinkage=eps_shrinkage or {},
        etas=etas if etas is not None else pd.DataFrame(),
        covariates=covariates if covariates is not None else pd.DataFrame(),
    )


@pytest.fixture
def make_results_factory():
    return make_results
