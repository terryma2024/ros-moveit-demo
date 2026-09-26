"""Legacy import path for pick-place validation."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.act.pick_place_validation_manifest"
)
