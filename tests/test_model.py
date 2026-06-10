from __future__ import annotations
from pathlib import Path
from pkflow.model import Model


def test_stem_falls_back_to_path_stem_when_no_name():
    m = Model(path=Path("/runs/run42.ctl"), backend="nonmem")
    assert m.stem == "run42"


def test_stem_prefers_explicit_name():
    m = Model(path=Path("/runs/run42.ctl"), backend="nonmem", name="mymodel")
    assert m.stem == "mymodel"


def test_dataset_defaults_to_none():
    m = Model(path=Path("x.ctl"), backend="nonmem")
    assert m.dataset is None


def test_raw_not_in_repr():
    m = Model(path=Path("x.ctl"), backend="nonmem", raw=object())
    assert "raw" not in repr(m)
