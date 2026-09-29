"""The build-receipt writer the Task 8L provenance step depends on.

`source_provenance` requires, for every `compiled` role, a receipt beside the artefact with exactly
`sources, headers, cmake_arguments, compiler, linker, dependency_sha256, output_sha256`, the first five
non-empty, a non-empty dependency map, and `output_sha256` equal to the artefact's own digest. A version
without its build provenance is not a verified artefact, so every gap here fails closed.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from so101_build_receipt import RECEIPT_SUFFIX, write_build_receipt  # noqa: E402

from so101_demo.act.source_provenance import _RECEIPT_FIELDS  # noqa: E402


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "libplugin.so"
    path.write_bytes(b"\x7fELF pretend plugin")
    return path


def _arguments(tmp_path: Path) -> dict:
    source = tmp_path / "plugin.cpp"
    source.write_text("int main(){return 0;}\n")
    header = tmp_path / "plugin.hpp"
    header.write_text("#pragma once\n")
    dependency = tmp_path / "libmujoco.so"
    dependency.write_bytes(b"\x7fELF dependency")
    return {"sources": [str(source)], "headers": [str(header)],
            "cmake_arguments": ["-DCMAKE_BUILD_TYPE=Release"],
            "compiler": "/usr/bin/c++", "linker": "/usr/bin/ld",
            "dependencies": {str(dependency): hashlib.sha256(dependency.read_bytes()).hexdigest()}}


def test_written_receipt_satisfies_the_source_provenance_contract(tmp_path):
    artifact = _artifact(tmp_path)
    receipt_path = write_build_receipt(artifact=artifact, **_arguments(tmp_path))
    assert receipt_path.name == artifact.name + RECEIPT_SUFFIX
    receipt = json.loads(receipt_path.read_text())
    assert set(receipt) == set(_RECEIPT_FIELDS)
    assert receipt["output_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert receipt["sources"] and receipt["headers"] and receipt["cmake_arguments"]
    assert receipt["compiler"] and receipt["linker"] and receipt["dependency_sha256"]


def test_output_digest_follows_the_artefact_not_the_caller(tmp_path):
    artifact = _artifact(tmp_path)
    write_build_receipt(artifact=artifact, **_arguments(tmp_path))
    artifact.write_bytes(b"\x7fELF different bytes")
    receipt = json.loads(Path(str(artifact) + RECEIPT_SUFFIX).read_text())
    # a receipt left beside a changed artefact must not agree with it, which is what SOURCE_PROVENANCE_INSTALL_DIRTY reports
    assert receipt["output_sha256"] != hashlib.sha256(artifact.read_bytes()).hexdigest()


@pytest.mark.parametrize("field", ["sources", "headers", "cmake_arguments", "compiler", "linker"])
def test_an_empty_required_field_is_refused(tmp_path, field):
    arguments = _arguments(tmp_path)
    arguments[field] = [] if field in ("sources", "headers", "cmake_arguments") else ""
    with pytest.raises(ValueError, match="BUILD_RECEIPT_FIELDS_INCOMPLETE"):
        write_build_receipt(artifact=_artifact(tmp_path), **arguments)


def test_an_empty_or_malformed_dependency_map_is_refused(tmp_path):
    arguments = _arguments(tmp_path)
    arguments["dependencies"] = {}
    with pytest.raises(ValueError, match="BUILD_RECEIPT_DEPENDENCIES_INVALID"):
        write_build_receipt(artifact=_artifact(tmp_path), **arguments)
    arguments["dependencies"] = {"/x/lib.so": "not-a-digest"}
    with pytest.raises(ValueError, match="BUILD_RECEIPT_DEPENDENCIES_INVALID"):
        write_build_receipt(artifact=_artifact(tmp_path), **arguments)


def test_a_missing_or_symlinked_artefact_is_refused(tmp_path):
    with pytest.raises(ValueError, match="BUILD_RECEIPT_ARTIFACT_MISSING"):
        write_build_receipt(artifact=tmp_path / "absent.so", **_arguments(tmp_path))
    real = _artifact(tmp_path)
    link = tmp_path / "link.so"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="BUILD_RECEIPT_ARTIFACT_MISSING"):
        write_build_receipt(artifact=link, **_arguments(tmp_path))
