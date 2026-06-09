"""Nonparametric case-resampling bootstrap.

Pure functions for the statistics (`resample_subjects`, `percentile_ci`,
`summarize_bootstrap`) plus an orchestrator (`bootstrap`) that wires
resample → run → collect → summarize over a backend + executor.

Resampling is by *subject*: draw N subjects with replacement and relabel each
draw to a fresh unique ID so duplicated subjects stay distinct (NONMEM merges
records that share an ID).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shutil
import numpy as np
import pandas as pd

from ..model import Model, Results


# ---- pure statistics -----------------------------------------------------
def resample_subjects(df: pd.DataFrame, id_col: str, rng: np.random.Generator) -> pd.DataFrame:
    """Case-resample subjects with replacement, relabelling to fresh 1..N IDs.

    Each drawn subject's full record block is kept intact; a subject drawn
    twice yields two blocks with two distinct new IDs.
    """
    ids = df[id_col].unique()
    drawn = rng.choice(ids, size=len(ids), replace=True)
    blocks = []
    for new_id, old_id in enumerate(drawn, start=1):
        block = df[df[id_col] == old_id].copy()
        block[id_col] = new_id
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def percentile_ci(values, level: float = 0.95) -> tuple[float, float]:
    """Two-sided percentile interval at the given coverage level."""
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(np.asarray(values, dtype=float), [alpha, 1.0 - alpha])
    return float(lo), float(hi)


def summarize_bootstrap(
    original: Results,
    replicates: list[Results],
    level: float = 0.95,
) -> pd.DataFrame:
    """One row per parameter: original estimate + bootstrap mean/median/SE/CI.

    Only replicates with status == "ok" contribute. `n_success` reports how
    many did. Raises if none converged.
    """
    ok = [r for r in replicates if r.status == "ok"]
    if not ok:
        raise ValueError("no successful replicates to summarize")

    # parameter name -> list of estimates across successful replicates
    samples: dict[str, list[float]] = {}
    for r in ok:
        for _, row in r.parameters.iterrows():
            samples.setdefault(row["name"], []).append(float(row["estimate"]))

    orig = {row["name"]: float(row["estimate"])
            for _, row in original.parameters.iterrows()}

    rows = []
    for name, vals in samples.items():
        arr = np.asarray(vals, dtype=float)
        lo, hi = percentile_ci(arr, level)
        rows.append({
            "name": name,
            "original_est": orig.get(name),
            "boot_mean": float(arr.mean()),
            "boot_median": float(np.median(arr)),
            "boot_se": float(arr.std(ddof=1)) if len(arr) > 1 else None,
            "ci_lo": lo,
            "ci_hi": hi,
            "n_success": len(arr),
        })
    return pd.DataFrame(rows)


# ---- orchestrator --------------------------------------------------------
@dataclass
class BootstrapResult:
    """Outcome of a bootstrap run: the summary table plus the raw per-replicate
    estimates, with how many of the N replicates converged."""
    n_total: int
    n_success: int
    level: float
    summary: pd.DataFrame
    replicate_params: pd.DataFrame

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.summary.to_csv(out_dir / "bootstrap_summary.csv", index=False)
        if not self.replicate_params.empty:
            self.replicate_params.to_parquet(out_dir / "replicate_params.parquet")


def _dataset_of(model: Model) -> pd.DataFrame:
    if model.raw is not None and hasattr(model.raw, "dataset"):
        return model.raw.dataset
    raise ValueError("no dataset available; pass dataset= explicitly")


def _id_col_of(model: Model) -> str:
    if model.raw is not None and hasattr(model.raw, "datainfo"):
        return model.raw.datainfo.id_column.name
    raise ValueError("could not infer id column; pass id_col= explicitly")


def bootstrap(
    model: Model,
    original: Results,
    backend,
    executor,
    run_dir: Path,
    *,
    n: int = 200,
    seed: int = 1234,
    level: float = 0.95,
    dataset: pd.DataFrame | None = None,
    id_col: str | None = None,
) -> BootstrapResult:
    """Run an N-replicate case-resampling bootstrap.

    For each replicate: resample subjects → write a headerless NONMEM-loadable
    CSV → run the model via `backend` (which copies the data + rewrites $DATA)
    → collect estimates. Replicate run dirs are deleted after collection; only
    the summary + per-replicate estimates are kept.
    """
    data = dataset if dataset is not None else _dataset_of(model)
    id_col = id_col or _id_col_of(model)
    rng = np.random.default_rng(seed)

    boot_dir = Path(run_dir) / "bootstrap"
    boot_dir.mkdir(parents=True, exist_ok=True)

    rep_results: list[Results] = []
    rep_rows: list[dict] = []
    for i in range(1, n + 1):
        rep_dir = boot_dir / f"rep_{i:03d}"
        rep_dir.mkdir(parents=True, exist_ok=True)
        csv = boot_dir / f"rep_{i:03d}.csv"
        resample_subjects(data, id_col, rng).to_csv(csv, index=False, header=False)

        rep_model = Model(path=model.path, backend=model.backend,
                          dataset=csv, name=model.name, raw=model.raw)
        handle = backend.run(rep_model, rep_dir, executor)
        r = backend.collect(rep_model, rep_dir, handle)
        rep_results.append(r)
        for _, row in r.parameters.iterrows():
            rep_rows.append({
                "replicate": i,
                "name": row["name"],
                "estimate": float(row["estimate"]),
                "status": r.status,
            })

        # clean up: keep estimates (in memory), drop the run dir + data file
        shutil.rmtree(rep_dir, ignore_errors=True)
        csv.unlink(missing_ok=True)

    summary = summarize_bootstrap(original, rep_results, level)
    result = BootstrapResult(
        n_total=n,
        n_success=sum(1 for r in rep_results if r.status == "ok"),
        level=level,
        summary=summary,
        replicate_params=pd.DataFrame(rep_rows),
    )
    result.save(boot_dir)
    return result
