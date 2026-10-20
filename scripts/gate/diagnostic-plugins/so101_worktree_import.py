"""Import so101_demo and so101_teleop from the real worktree directories (no symlink in the module path).

Some tests (the audit reader) refuse a symlinked path component, so the symlinked `test-import` root cannot be the
module location. Loaded with `-p so101_worktree_import` on the pytest command line (also in xdist workers).
"""
import importlib.util
import os
import sys
from pathlib import Path

# The worktree is the repository this file lives in (scripts/gate/diagnostic-plugins); SO101_WORKTREE overrides it.
WORKTREE = os.environ.get("SO101_WORKTREE") or str(Path(__file__).resolve().parents[3])
PACKAGES = {
    "so101_demo": WORKTREE + "/src/so101_demo_py/src",
    "so101_teleop": WORKTREE + "/src/so101_teleop/so101_teleop",
}


def _register():
    for name, directory in PACKAGES.items():
        existing = sys.modules.get(name)
        if existing is not None and str(getattr(existing, "__file__", "")).startswith(directory):
            continue
        spec = importlib.util.spec_from_file_location(
            name, directory + "/__init__.py", submodule_search_locations=[directory])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)


_register()
