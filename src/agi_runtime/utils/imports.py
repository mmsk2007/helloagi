from __future__ import annotations

from importlib.util import find_spec


def module_available(module_name: str) -> bool:
    """Return True when an optional module can be imported by name.

    ``find_spec("pkg.submodule")`` raises ``ModuleNotFoundError`` when the
    parent namespace package is absent, so callers that probe optional extras
    must treat that the same as "module not installed" rather than crashing.
    """
    try:
        return find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


__all__ = ["module_available"]
