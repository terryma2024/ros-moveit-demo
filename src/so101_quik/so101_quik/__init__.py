"""Load the independent, frozen QuIK C ABI without ROS or NumPy imports."""

import ctypes
from pathlib import Path
import sys

__version__ = "0.1.0"


def load_native_library() -> tuple[ctypes.CDLL, Path]:
    """Return typed symbols and their actual package-owned shared library path.

    Buffer layouts and context ownership are documented in so101_quik/c_api.h.
    Calls on one context must be serialized by its owner.
    """
    if sys.platform not in ("linux", "darwin"):
        raise ImportError(f"QUIK_LIBRARY_UNAVAILABLE: unsupported platform {sys.platform}")
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    artifact = Path(__file__).resolve().parent / "lib" / ("libso101_quik_core" + suffix)
    try:
        library = ctypes.CDLL(str(artifact))
        pointer = ctypes.POINTER(ctypes.c_double)
        library.quik_create.argtypes = [pointer, pointer, pointer, ctypes.c_int]
        library.quik_create.restype = ctypes.c_void_p
        library.quik_destroy.argtypes = [ctypes.c_void_p]
        library.quik_destroy.restype = None
        library.quik_fk.argtypes = [ctypes.c_void_p, pointer, pointer]
        library.quik_fk.restype = ctypes.c_int
        library.quik_solve.argtypes = [
            ctypes.c_void_p, pointer, pointer, pointer, pointer,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ]
        library.quik_solve.restype = ctypes.c_int
    except (OSError, AttributeError) as error:
        raise ImportError(f"QUIK_LIBRARY_UNAVAILABLE: {artifact}: {error}") from error
    return library, artifact
