from __future__ import annotations

from importlib.util import find_spec


def module_available(module_name: str) -> bool:
    """Return whether an optional module can be imported.

    importlib.util.find_spec() raises ModuleNotFoundError for dotted module
    names when the parent namespace package does not exist. Optional feature
    probes should treat that as "module unavailable", not as a hard failure.
    """

    try:
        return find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
