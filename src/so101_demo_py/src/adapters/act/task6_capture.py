"""Legacy import path for synchronized camera capture."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.adapters.act.synchronized_frame_capture"
)
