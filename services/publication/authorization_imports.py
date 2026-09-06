"""Expose only the verified services namespace, never the repository root."""
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec
from pathlib import Path
import sys


def install():
    location = str(Path(__file__).resolve().parents[1])
    existing = sys.modules.get('services')
    if existing is not None:
        if set(getattr(existing, '__path__', ())) != {location}:
            raise RuntimeError('authorization services import root invalid')
        return
    spec = ModuleSpec('services', loader=None, is_package=True)
    spec.submodule_search_locations = [location]
    sys.modules['services'] = module_from_spec(spec)


install()
