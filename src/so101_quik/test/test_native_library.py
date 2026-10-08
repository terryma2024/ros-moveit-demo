"""The installed QuIK package must work without a robot-demo dependency."""

import ctypes
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def kernel():
    try:
        package = importlib.import_module("so101_quik")
    except ImportError as error:
        pytest.fail(f"independent QuIK package is unavailable: {error}")
    library, artifact = package.load_native_library()
    return package, library, artifact


def matrix(values):
    return (ctypes.c_double * 16)(*values)


IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
DH = (0.1, 0, 0, 0, 0.2, 0, 0, 0, 0.1, 0, 0, 0,
      0.1, 0, 0, 0, 0.1, 0, 0, 0)


def context(library, base=IDENTITY, tool=IDENTITY):
    result = library.quik_create((ctypes.c_double * 20)(*DH), matrix(base), matrix(tool), 0)
    assert result, "QuIK context initialization failed"
    return result


def test_fk_preserves_row_major_geometry_and_distinct_contexts():
    _, library, _ = kernel()
    first = context(library)
    base = (1, 0, 0, 0.1, 0, 1, 0, 0.2, 0, 0, 1, 0.3, 0, 0, 0, 1)
    tool = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0.04, 0, 0, 0, 1)
    second = context(library, base, tool)
    q = (ctypes.c_double * 5)(0, 0, 0, 0, math.pi / 2)
    expected = (0, -1, 0, 0.5, 1, 0, 0, 0.1, 0, 0, 1, 0, 0, 0, 0, 1)
    shifted = (0, -1, 0, 0.6, 1, 0, 0, 0.3, 0, 0, 1, 0.34, 0, 0, 0, 1)
    try:
        for handle, want in ((first, expected), (second, shifted), (first, expected)):
            actual = (ctypes.c_double * 16)()
            assert library.quik_fk(handle, q, actual) == 0
            assert tuple(actual) == pytest.approx(want, abs=1e-12)
    finally:
        library.quik_destroy(second)
        library.quik_destroy(first)


def test_solve_reaches_nonzero_hand_checked_pose_from_zero_seed():
    _, library, _ = kernel()
    handle = context(library)
    # Rotating the first joint by pi/6 places the 0.6 m planar chain here.
    target = matrix((0.8660254037844386, -0.5, 0, 0.5196152422706632,
                     0.5, 0.8660254037844386, 0, 0.3,
                     0, 0, 1, 0, 0, 0, 0, 1))
    seed, output = (ctypes.c_double * 5)(), (ctypes.c_double * 5)()
    residual = (ctypes.c_double * 6)()
    iterations, reason = ctypes.c_int(), ctypes.c_int()
    try:
        assert library.quik_solve(handle, target, seed, output, residual,
                                  ctypes.byref(iterations), ctypes.byref(reason)) == 0
        assert all(math.isfinite(value) for value in (*output, *residual))
        actual = (ctypes.c_double * 16)()
        assert library.quik_fk(handle, output, actual) == 0
        assert tuple(actual) == pytest.approx(tuple(target), abs=1e-8)
    finally:
        library.quik_destroy(handle)


def run_without_site(site, code):
    return subprocess.run([sys.executable, "-S", "-c",
                           f"import sys; sys.path.insert(0, {str(site)!r});\n" + code],
                          text=True, capture_output=True, timeout=20,
                          env={**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"})


def test_python_loader_and_native_fk_need_no_demo_numpy_or_ros():
    package, _, _ = kernel()
    result = run_without_site(Path(package.__file__).parent.parent, '''
import ctypes, json
from so101_quik import load_native_library
library, artifact = load_native_library()
dh = (ctypes.c_double * 20)(0.1,0,0,0, 0.2,0,0,0, 0.1,0,0,0, 0.1,0,0,0, 0.1,0,0,0)
identity = (ctypes.c_double * 16)(1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
context = library.quik_create(dh, identity, identity, 0)
assert context
out = (ctypes.c_double * 16)()
try:
    assert library.quik_fk(context, (ctypes.c_double * 5)(), out) == 0
    print(json.dumps({'x': out[3], 'foreign_modules': [m for m in ('so101_demo','numpy','rclpy','ament_index_python') if m in sys.modules]}))
finally:
    library.quik_destroy(context)
''')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc["x"] == pytest.approx(0.6, abs=1e-12)
    assert doc["foreign_modules"] == []


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_unloadable_library_is_explicit(tmp_path, corrupt):
    package, _, artifact = kernel()
    copied = tmp_path / "so101_quik"
    copied.mkdir()
    shutil.copy2(package.__file__, copied / "__init__.py")
    if corrupt:
        (copied / "lib").mkdir()
        (copied / "lib" / artifact.name).write_bytes(b"not a shared library")
    result = run_without_site(tmp_path, '''
from so101_quik import load_native_library
try:
    load_native_library()
except ImportError as error:
    assert str(error).startswith('QUIK_LIBRARY_UNAVAILABLE:')
    print('explicit-error')
else:
    raise AssertionError('missing/corrupt package data was accepted')
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "explicit-error"
