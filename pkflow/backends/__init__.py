from .base import Backend, RunHandle
from .nonmem import NonmemBackend

_REGISTRY: dict[str, Backend] = {
    "nonmem": NonmemBackend(),
}


def get(name: str) -> Backend:
    if name not in _REGISTRY:
        raise KeyError(f"unknown backend: {name!r}. available: {list(_REGISTRY)}")
    return _REGISTRY[name]


__all__ = ["Backend", "RunHandle", "get"]
