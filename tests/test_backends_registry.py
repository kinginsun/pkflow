from __future__ import annotations
from pathlib import Path
import pytest

from pkflow import backends
from pkflow.backends import Backend, RunHandle
from pkflow.backends.nonmem import NonmemBackend


def test_get_returns_nonmem_backend():
    be = backends.get("nonmem")
    assert isinstance(be, NonmemBackend)
    assert be.name == "nonmem"


def test_get_unknown_backend_raises():
    with pytest.raises(KeyError, match="unknown backend"):
        backends.get("does_not_exist")


def test_nonmem_satisfies_backend_protocol():
    assert isinstance(NonmemBackend(), Backend)


def test_runhandle_stores_returncode_and_extra():
    h = RunHandle(run_dir=Path("/runs/a"), returncode=0, lst=Path("a.lst"))
    assert h.run_dir == Path("/runs/a")
    assert h.returncode == 0
    assert h.extra["lst"] == Path("a.lst")


def test_runhandle_returncode_defaults_none():
    h = RunHandle(run_dir=Path("/runs/a"))
    assert h.returncode is None
    assert h.extra == {}
