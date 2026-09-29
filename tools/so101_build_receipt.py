"""Write the build receipt that `source_provenance` requires beside every compiled artefact.

A compiled role is only verified when the artefact is accompanied by a record of how it was produced: its
sources, headers, CMake arguments, compiler, linker, dependency digests, and the artefact's own digest. The
receipt is written beside the artefact as `<artefact>.build-receipt.json`, which is exactly where the verifier
looks for it. Every gap fails closed, because an artefact without its build provenance is not a pin.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

RECEIPT_SUFFIX = ".build-receipt.json"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SEQUENCE_FIELDS = ("sources", "headers", "cmake_arguments")
_STRING_FIELDS = ("compiler", "linker")


def _regular(path: Path) -> None:
    try:
        info = Path(path).stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError("BUILD_RECEIPT_ARTIFACT_MISSING") from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("BUILD_RECEIPT_ARTIFACT_MISSING")


def _digest(path: Path) -> str:
    stream = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(stream, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def write_build_receipt(*, artifact, sources, headers, cmake_arguments, compiler, linker,
                        dependencies) -> Path:
    """Record how `artifact` was built, beside it, in the shape the provenance verifier accepts."""

    artifact = Path(artifact)
    _regular(artifact)
    for name, value in (("sources", sources), ("headers", headers),
                        ("cmake_arguments", cmake_arguments)):
        if not isinstance(value, (list, tuple)) or not value or any(not str(item) for item in value):
            raise ValueError(f"BUILD_RECEIPT_FIELDS_INCOMPLETE: {name}")
    for name, value in (("compiler", compiler), ("linker", linker)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"BUILD_RECEIPT_FIELDS_INCOMPLETE: {name}")
    if not isinstance(dependencies, dict) or not dependencies:
        raise ValueError("BUILD_RECEIPT_DEPENDENCIES_INVALID")
    for relative, digest in dependencies.items():
        if not isinstance(relative, str) or not relative or _SHA256.fullmatch(str(digest)) is None:
            raise ValueError("BUILD_RECEIPT_DEPENDENCIES_INVALID")
    receipt = {
        "sources": [str(item) for item in sources],
        "headers": [str(item) for item in headers],
        "cmake_arguments": [str(item) for item in cmake_arguments],
        "compiler": compiler,
        "linker": linker,
        "dependency_sha256": {str(key): str(value) for key, value in dependencies.items()},
        "output_sha256": _digest(artifact),
    }
    target = Path(str(artifact) + RECEIPT_SUFFIX)
    target.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    return target
