"""Legacy entry point for synchronized ACT RGB capture."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.cli.act_capture_synchronized_rgb"
)
