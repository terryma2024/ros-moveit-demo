"""Setup must enforce isolation and integrity before compiling or installing."""

import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import tarfile

import pytest
from paths import REPOSITORY


REPO = REPOSITORY
ENTRY = REPO / "scripts/setup-so101-quik.sh"
HELPER = REPO / "scripts/so101_quik_setup.py"


def entry(*args):
    assert ENTRY.is_file(), "formal QuIK setup entry is missing"
    return subprocess.run(["bash", str(ENTRY), *map(str, args)], text=True,
                          capture_output=True, timeout=20)


def helper():
    assert HELPER.is_file(), "QuIK dependency integrity helper is missing"
    spec = importlib.util.spec_from_file_location("quik_setup_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_explains_standalone_and_ros_python_options_without_installing():
    result = entry("--help")
    assert result.returncode == 0, result.stderr
    assert "--prefix" in result.stdout and "--python" in result.stdout
    assert "Ubuntu 24.04" in result.stdout and "Apple Silicon" in result.stdout


def test_setup_refuses_nonempty_unmanaged_prefix_without_touching_it(tmp_path):
    prefix = tmp_path / "existing"
    prefix.mkdir()
    sentinel = prefix / "user-data"
    sentinel.write_bytes(b"preserve me")
    result = entry("--prefix", prefix)
    assert result.returncode != 0
    assert "UNMANAGED_PREFIX" in result.stderr
    assert sorted(prefix.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"preserve me"


def test_setup_refuses_prefix_inside_source_checkout():
    result = entry("--prefix", REPO)
    assert result.returncode != 0
    assert "UNSAFE_PREFIX" in result.stderr


def test_rejected_nested_checkout_prefix_does_not_create_parent_directories(tmp_path):
    checkout = tmp_path / "checkout"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    assert ENTRY.is_file()
    script = scripts / ENTRY.name
    shutil.copy2(ENTRY, script)
    result = subprocess.run(["bash", str(script), "--prefix", str(checkout / "new/sub/install")],
                            text=True, capture_output=True, timeout=20)
    assert result.returncode != 0 and "UNSAFE_PREFIX" in result.stderr
    assert not (checkout / "new").exists()


def test_setup_refuses_symlink_prefix_without_touching_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    prefix = tmp_path / "link"
    prefix.symlink_to(target, target_is_directory=True)
    result = entry("--prefix", prefix)
    assert result.returncode != 0
    assert "UNSAFE_PREFIX" in result.stderr
    assert not list(target.iterdir())


def test_failed_download_stops_explicitly_before_python_or_build(tmp_path):
    # Reproduce an external peer failure without contacting the network in ordinary tests.
    tools = tmp_path / "tools"
    tools.mkdir()
    curl = tools / "curl"
    curl.write_text("#!/bin/sh\nexit 56\n")
    curl.chmod(0o755)
    prefix = tmp_path / "install"
    assert ENTRY.is_file()
    result = subprocess.run(["bash", str(ENTRY), "--prefix", str(prefix)], text=True,
                            capture_output=True, timeout=20,
                            env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]})
    assert result.returncode != 0 and "UV_DOWNLOAD_FAILED" in result.stderr
    assert not (prefix / "env").exists()
    assert not (prefix / "manifest.json").exists()


def test_checksum_rejects_corrupt_dependency_before_extraction(tmp_path):
    artifact = tmp_path / "dependency.tar.gz"
    artifact.write_bytes(b"corrupt download")
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        helper().verify_sha256(artifact, hashlib.sha256(b"expected").hexdigest())


def test_verified_dependency_hash_is_returned(tmp_path):
    artifact = tmp_path / "dependency.tar.gz"
    artifact.write_bytes(b"verified dependency")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert helper().verify_sha256(artifact, digest) == digest


@pytest.mark.parametrize("name", ["../escape", "/absolute/escape"])
def test_archive_cannot_write_outside_dependency_directory(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo(name)
        member.size = 3
        stream.addfile(member, io.BytesIO(b"bad"))
    destination = tmp_path / "headers"
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE"):
        helper().extract_archive(archive, destination)
    assert not (tmp_path / "escape").exists()


def test_archive_cannot_install_links(tmp_path):
    archive = tmp_path / "link.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("Eigen/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/usr/local"
        stream.addfile(member)
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE"):
        helper().extract_archive(archive, tmp_path / "headers")


def test_archive_extracts_real_header_bytes(tmp_path):
    archive = tmp_path / "headers.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("eigen-3.4.0/Eigen/Core")
        member.size = 6
        stream.addfile(member, io.BytesIO(b"header"))
    destination = tmp_path / "headers"
    helper().extract_archive(archive, destination)
    assert (destination / "eigen-3.4.0/Eigen/Core").read_bytes() == b"header"


def test_rerun_rejects_missing_or_modified_installed_artifact(tmp_path):
    binary = tmp_path / "_quik_native.so"
    binary.write_bytes(b"compiled artifact")
    artifacts = {str(binary): hashlib.sha256(binary.read_bytes()).hexdigest()}
    helper().verify_artifacts(artifacts)
    binary.write_bytes(b"modified artifact")
    with pytest.raises(ValueError, match="INSTALLED_ARTIFACT_MISMATCH"):
        helper().verify_artifacts(artifacts)
    binary.unlink()
    with pytest.raises(ValueError, match="INSTALLED_ARTIFACT_MISSING"):
        helper().verify_artifacts(artifacts)


def test_setup_fingerprint_tracks_independent_quik_build_inputs(tmp_path):
    repo = tmp_path / "repo"
    for package, files in {
        "so101_demo_py": ("setup.py", "setup.cfg", "MANIFEST.in", "package.xml", "src/__init__.py"),
        "so101_quik": ("setup.py", "pyproject.toml", "MANIFEST.in", "package.xml",
                       "CMakeLists.txt", "src/quik_c_api.cpp", "so101_quik/__init__.py"),
    }.items():
        for name in files:
            path = repo / "src" / package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original build input")
    for name in ("setup-so101-quik.sh", "so101_quik_setup.py", "so101-quik-bootstrap.lock.env"):
        path = repo / "scripts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("bootstrap input")
    first = helper().source_inputs(repo)
    (repo / "src/so101_quik/src/quik_c_api.cpp").write_text("changed core input")
    second = helper().source_inputs(repo)
    assert first != second, "rerun would reuse a stale independent QuIK kernel"
