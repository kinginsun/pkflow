from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

BackendName = Literal["nonmem", "mmdl", "stan", "nlmixr2"]


@dataclass
class Model:
    """Backend-agnostic model handle. Parsed once, consumed by run/diagnose/report."""
    path: Path
    backend: BackendName
    dataset: Path | None = None
    name: str = ""
    raw: object | None = field(default=None, repr=False)  # backend-native object (e.g. pharmpy Model)

    @property
    def stem(self) -> str:
        return self.name or self.path.stem
