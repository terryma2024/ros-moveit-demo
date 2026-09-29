"""Task 8P1: source provenance is closed, canonical and tamper-evident."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from so101_demo.act.source_provenance import (
    build_source_provenance, runtime_role_specs, verify_source_provenance,
    write_source_provenance,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _receipt(installed: Path, source_rel: str, source_root: Path) -> dict:
    """A receipt whose declared inputs really exist, so a 1-byte edit is detectable."""

    return {
        "sources": [source_rel], "headers": [source_rel],
        "cmake_arguments": ["-DCMAKE_BUILD_TYPE=Release"], "compiler": "g++ 13.3.0",
        "linker": "ld 2.42",
        "dependency_sha256": {source_rel: _sha((source_root / source_rel).read_bytes())},
        "output_sha256": _sha(installed.read_bytes()),
    }


@pytest.fixture
def provenance_env(tmp_path):
    """A real git tree plus an overlay carrying every registered runtime role."""

    source_root = tmp_path / "repo"
    overlay = tmp_path / "install"
    source_root.mkdir()
    dependency = tmp_path / "dependency"
    for logical_name, kind, source_rel, install_rel, owning_overlay in runtime_role_specs():
        if kind == "external_runtime":
            continue
        root = dependency if owning_overlay == "dependency" else overlay
        payload = f"# {logical_name}\n".encode()
        if kind == "compiled":
            # a compiled role's source may be a directory (its package's source root), so plant one real file
            source_path = source_root / source_rel
            if source_path.suffix:
                if not source_path.exists():
                    _write(source_path, payload)
            else:
                source_path = source_path / f"{logical_name}_source.cpp"
                _write(source_path, payload)
            installed = _write(root / install_rel, payload + b"binary\n")
            _write(Path(str(installed) + ".build-receipt.json"),
                   json.dumps(_receipt(installed, str(source_path.relative_to(source_root)), source_root)).encode())
        else:
            _write(source_root / source_rel, payload)
            _write(root / install_rel, payload)
    subprocess.run(["git", "init", "-q"], cwd=source_root, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "add", "-A"], cwd=source_root, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "commit", "-qm", "fixture"], cwd=source_root, check=True)
    head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return source_root, overlay, head


def _document(source_root, overlay, head):
    return build_source_provenance(source_root, overlay, calibration_identity=(head, "b" * 64),
                                   dependency_overlay=source_root.parent / "dependency")


def test_provenance_rejects_changed_controlled_source(provenance_env):
    source_root, overlay, head = provenance_env
    document = _document(source_root, overlay, head)
    controlled = source_root / runtime_role_specs()[0][2]
    controlled.write_bytes(controlled.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SOURCE_PROVENANCE_DIRTY"):
        verify_source_provenance(document, source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")


def test_provenance_requires_every_registered_role(provenance_env):
    source_root, overlay, head = provenance_env
    document = _document(source_root, overlay, head)
    roles = document["runtime_roles"]
    assert [role["logical_name"] for role in roles] == sorted(
        spec[0] for spec in runtime_role_specs())
    with pytest.raises(ValueError):
        verify_source_provenance(dict(document, runtime_roles=roles[1:]),
                                 source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")
    with pytest.raises(ValueError):
        verify_source_provenance(dict(document, runtime_roles=[roles[0], *roles]),
                                 source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")


def test_provenance_rejects_verbatim_install_byte_mismatch(provenance_env):
    source_root, overlay, head = provenance_env
    document = _document(source_root, overlay, head)
    verbatim = [role for role in document["runtime_roles"]
                if role["artifact_kind"] == "verbatim_install"]
    assert verbatim
    installed = Path(verbatim[0]["installed_path"])
    installed.write_bytes(installed.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        verify_source_provenance(document, source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")


def test_provenance_rejects_incomplete_compiled_receipt(provenance_env):
    source_root, overlay, head = provenance_env
    document = _document(source_root, overlay, head)
    compiled = [role for role in document["runtime_roles"] if role["artifact_kind"] == "compiled"]
    assert compiled, "the registry must cover compiled roles"
    broken = json.loads(json.dumps(document))
    for role in broken["runtime_roles"]:
        if role["artifact_kind"] == "compiled":
            role.pop("build_receipt_path")
            break
    with pytest.raises(ValueError):
        verify_source_provenance(broken, source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")
    receipt = Path(compiled[0]["build_receipt_path"])
    payload = json.loads(receipt.read_bytes())
    payload["compiler"] = ""
    receipt.write_bytes(json.dumps(payload).encode())
    with pytest.raises(ValueError):
        verify_source_provenance(document, source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")


def test_provenance_is_canonical_and_deterministic(provenance_env, tmp_path):
    source_root, overlay, head = provenance_env
    first = write_source_provenance(_document(source_root, overlay, head), tmp_path / "a.json")
    second = write_source_provenance(_document(source_root, overlay, head), tmp_path / "b.json")
    raw = first.read_bytes()
    assert raw == second.read_bytes()
    assert raw.endswith(b"\n") and b", " not in raw and b": " not in raw
    document = json.loads(raw)
    assert raw == (json.dumps(document, sort_keys=True, separators=(",", ":"),
                             allow_nan=False) + "\n").encode()
    with pytest.raises(ValueError):
        write_source_provenance(document, first)


def test_provenance_rejects_extra_fields_and_role_shape(provenance_env):
    source_root, overlay, head = provenance_env
    document = _document(source_root, overlay, head)
    with pytest.raises(ValueError):
        verify_source_provenance(dict(document, unexpected=1),
                                 source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")
    broken = json.loads(json.dumps(document))
    broken["runtime_roles"][0].pop("logical_name")
    with pytest.raises(ValueError):
        verify_source_provenance(broken, source_root=source_root, install_overlay=overlay, dependency_overlay=source_root.parent / "dependency")
