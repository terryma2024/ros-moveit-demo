"""Verify package imports keep GUI tooling independent from server models."""

import os
import subprocess
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_gui_import_does_not_load_server_models():
    """Importing GUI helpers must not pull in Pydantic server models."""
    script = """
import importlib.abc
import sys


class RejectServerModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'so101_teleop.models':
            raise AssertionError('GUI import loaded server-only models')
        return None


sys.meta_path.insert(0, RejectServerModels())
import so101_teleop.gui.x11
assert 'so101_teleop.models' not in sys.modules
"""
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join(
        filter(None, (str(PACKAGE_ROOT), environment.get('PYTHONPATH')))
    )

    result = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
