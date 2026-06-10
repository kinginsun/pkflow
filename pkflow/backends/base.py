from __future__ import annotations
from pathlib import Path
from typing import Protocol, runtime_checkable
import pandas as pd
from ..model import Model, Results


@runtime_checkable
class Backend(Protocol):
    """Every backend implements this. parse → run → collect."""
    name: str

    def parse(self, path: Path) -> Model: ...

    def run(self, model: Model, run_dir: Path, executor) -> "RunHandle": ...

    def collect(self, model: Model, run_dir: Path, handle: "RunHandle") -> Results: ...

    def simulate(
        self,
        model: Model,
        results: Results,
        run_dir: Path,
        executor,
        n_sim: int = 500,
        seed: int = 1234,
    ) -> pd.DataFrame:
        """Run N replicate simulations using fitted parameter estimates.

        Returns a long DataFrame with columns: REPLICATE, ID, TIME, DV
        (plus any stratification columns the user may need).
        """
        ...


class RunHandle:
    """Opaque token returned by Backend.run, consumed by collect.
    Carries whatever the executor needs to know about an in-flight job."""
    def __init__(self, run_dir: Path, returncode: int | None = None, **extra):
        self.run_dir = run_dir
        self.returncode = returncode
        self.extra = extra
