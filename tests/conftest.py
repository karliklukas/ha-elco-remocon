"""Load the HA-free modules (api, const, values) without importing Home Assistant."""

import importlib
import sys
import types
from pathlib import Path

PKG = "elco_ro"
_dir = Path(__file__).resolve().parents[1] / "custom_components" / "elco_remocon_ro"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(_dir)]  # package without running __init__.py (which needs homeassistant)
    sys.modules[PKG] = pkg

api = importlib.import_module(f"{PKG}.api")
const = importlib.import_module(f"{PKG}.const")
values = importlib.import_module(f"{PKG}.values")
energy_values = importlib.import_module(f"{PKG}.energy_values")
