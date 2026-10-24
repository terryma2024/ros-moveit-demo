"""Private build/install and verification for setup-so101-quik.sh."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"SHA256_MISMATCH: {path}: expected {expected}, got {actual}")
    return actual


def extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        for member in members:
            if (member.name.startswith("/") or ".." in Path(member.name).parts or
                    not (member.isfile() or member.isdir())):
                raise ValueError(f"UNSAFE_ARCHIVE: {member.name}")
        destination.mkdir(parents=True, exist_ok=True)
        # All members were checked, including rejection of links and special files.
        stream.extractall(destination, members=members)


def verify_artifacts(artifacts: dict[str, str]) -> None:
    for filename, expected in artifacts.items():
        path = Path(filename)
        if not path.is_file():
            raise ValueError(f"INSTALLED_ARTIFACT_MISSING: {path}")
        if digest(path) != expected:
            raise ValueError(f"INSTALLED_ARTIFACT_MISMATCH: {path}")


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_inputs(repo: Path) -> dict[str, str]:
    inputs = []
    for package_name, metadata, directories in (
        ("so101_demo_py", ("setup.py", "setup.cfg", "MANIFEST.in", "package.xml"),
         ("src", "config", "assets", "launch", "resource")),
        ("so101_quik", ("setup.py", "pyproject.toml", "MANIFEST.in", "package.xml", "CMakeLists.txt"),
         ("src", "config", "cmake", "include", "so101_quik", "third_party", "test")),
    ):
        package = repo / "src" / package_name
        inputs.extend(package / name for name in metadata)
        for name in directories:
            inputs.extend(path for path in (package / name).rglob("*")
                          if path.is_file() and "__pycache__" not in path.parts)
        for link in package.rglob("*"):
            if link.is_symlink() and not link.is_file():
                raise ValueError(f"SOURCE_RESOURCE_MISSING: {link}; clone with --recurse-submodules")
    inputs.extend(repo / "scripts" / name for name in (
        "setup-so101-quik.sh",
        "so101_quik_setup.py", "so101-quik-bootstrap.lock.env"))
    return {str(path.relative_to(repo)): digest(path) for path in sorted(inputs)}


def run(command: list[str], log: Path, *, cwd=None, env=None) -> None:
    print("+ " + shlex.join(command), flush=True)
    with log.open("w") as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        print(log.read_text()[-8000:], file=sys.stderr)
        raise RuntimeError(f"SETUP_COMMAND_FAILED: exit {result.returncode}; {log}")


def smoke(prefix: Path, expected_versions: dict[str, str]) -> dict:
    for name, expected in expected_versions.items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError(f"DEPENDENCY_VERSION_MISMATCH: {name}={actual}, expected {expected}")
    from so101_demo.control.moveit.pose_ik import create_pose_ik, describe_pose_ik

    urdf = prefix / "env/share/so101_demo_py/assets/mujoco/so101.urdf"
    kernels = {}
    for name in ("_ik_numeric",):
        module = importlib.import_module("so101_demo.control.moveit." + name)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(prefix / "env"):
            raise ValueError(f"INSTALLED_PREFIX_MISMATCH: {path}")
        kernels[str(path)] = digest(path)
    from so101_quik import load_native_library
    _, quik_path = load_native_library()
    if not quik_path.is_relative_to(prefix / "env"):
        raise ValueError(f"INSTALLED_PREFIX_MISMATCH: {quik_path}")
    kernels[str(quik_path)] = digest(quik_path)
    reference = create_pose_ik(urdf, ("1", "2", "3", "4", "5"), "world", "so101_tcp", backend="native")
    if reference._numeric is None:
        raise ValueError("NATIVE_KERNEL_NOT_ACTIVE")
    targets = [(0.0, 0.4, 0.2, 0.8, 0.0), (0.1, 0.3, 0.1, 0.6, 0.1)]
    results = {}
    for backend in ("native", "quik"):
        solver = create_pose_ik(urdf, ("1", "2", "3", "4", "5"), "world", "so101_tcp", backend=backend)
        cases = []
        for q_target in targets:
            target = reference.forward(q_target)
            q = solver.solve(target, (0.0,) * 5)
            actual = reference.forward(q)
            position = math.dist(actual.position_m, target.position_m)
            orientation = reference.orientation_error_rad(actual, target)
            if not (all(math.isfinite(v) for v in q) and position <= 0.002 and
                    orientation <= 0.10 and all(lo + 0.002 <= v <= hi - 0.002
                    for v, (lo, hi) in zip(q, solver.joint_limits, strict=True))):
                raise ValueError(f"INSTALLED_SOLVE_GATE_FAILED: {backend}")
            cases.append({"target_joints": q_target, "solution": q,
                          "position_error_m": position, "orientation_error_rad": orientation})
        provenance = describe_pose_ik(solver)
        for artifact in provenance["artifacts"].values():
            path = Path(artifact["path"])
            if not path.is_relative_to(prefix / "env"):
                raise ValueError(f"INSTALLED_PREFIX_MISMATCH: {path}")
            kernels[str(path)] = digest(path)
        results[backend] = {"cases": cases, "provenance": provenance}
    return {"artifacts": kernels, "solvers": results, "versions": expected_versions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--base-python", required=True)
    args = parser.parse_args()
    prefix, repo = args.prefix.resolve(), args.repo.resolve()
    if Path(sys.prefix).resolve() != prefix / "env":
        raise ValueError("SETUP_REQUIRES_PRIVATE_VENV")
    if Path(sys._base_executable).resolve() != Path(args.base_python).resolve():
        raise ValueError("PYTHON_BASE_MISMATCH: use the original interpreter or a fresh prefix")
    inputs = source_inputs(repo)
    numpy_pins = []
    for line in (repo / "src/so101_demo_py/config/ik/requirements.lock").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r'numpy==([0-9.]+);\s*sys_platform == "(linux|darwin)"', line)
        if not match:
            raise ValueError("UNSUPPORTED_IK_REQUIREMENT: " + line)
        if match[2] == sys.platform:
            numpy_pins.append(match[1])
    if len(numpy_pins) != 1:
        raise ValueError("AMBIGUOUS_NUMPY_PIN")
    numpy_version = numpy_pins[0]
    expected = {"numpy": numpy_version,
                "setuptools": os.environ["QUIK_SETUP_SETUPTOOLS"],
                "wheel": os.environ["QUIK_SETUP_WHEEL"],
                "cmake": os.environ["QUIK_SETUP_CMAKE"],
                "so101-quik": "0.1.0",
                "typing_extensions": os.environ["QUIK_SETUP_TYPING_EXTENSIONS"],
                "PyYAML": os.environ["QUIK_SETUP_PYYAML"]}
    manifest = prefix / "manifest.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous["source_inputs"] != inputs or previous["versions"] != expected:
            raise ValueError("SETUP_INPUT_MISMATCH: use a fresh prefix for changed sources or pins")
        verify_artifacts(previous["artifacts"])
        verified = smoke(prefix, expected)
        write_json(prefix / "verification-latest.json", {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "mode": "rerun", **verified})
        print("Both installed backends verified; existing installation reused.")
        return

    uv = str(prefix / "bin/uv")
    constraints = prefix / "requirements.lock"
    constraints.write_text("".join(f"{name}=={version}\n" for name, version in expected.items()
                                  if name != "so101-quik"))
    run([uv, "pip", "install", "--python", sys.executable, "--default-index", args.index,
         "--no-deps", "-r", str(constraints)], prefix / "logs/python-dependencies.log")
    eigen_archive = prefix / "downloads/eigen-3.4.0.tar.gz"
    if not eigen_archive.exists():
        partial = eigen_archive.with_suffix(".gz.part")
        run(["curl", "--fail", "--location", "--retry", "3", "--connect-timeout", "30",
             "--max-time", "600", "--speed-time", "30", "--speed-limit", "1024",
             os.environ["QUIK_SETUP_EIGEN_URL"], "-o", str(partial)], prefix / "logs/eigen-download.log")
        verify_sha256(partial, os.environ["QUIK_SETUP_EIGEN_SHA256"])
        partial.rename(eigen_archive)
    verify_sha256(eigen_archive, os.environ["QUIK_SETUP_EIGEN_SHA256"])
    extract_archive(eigen_archive, prefix / "dependencies")
    eigen = prefix / "dependencies/eigen-3.4.0"
    env = dict(os.environ, PATH=str(prefix / "env/bin") + os.pathsep + os.environ["PATH"])
    cmake = str(prefix / "env/bin/cmake")
    eigen_install = prefix / "dependencies/eigen-install"
    run([cmake, "-S", str(eigen), "-B", str(prefix / "build/eigen"),
         "-DBUILD_TESTING=OFF", "-DEIGEN_BUILD_DOC=OFF", f"-DCMAKE_INSTALL_PREFIX={eigen_install}"],
        prefix / "logs/eigen-configure.log", env=env)
    run([cmake, "--install", str(prefix / "build/eigen")],
        prefix / "logs/eigen-install.log", env=env)
    env["Eigen3_DIR"] = str(eigen_install / "share/eigen3/cmake")
    source = prefix / "source"
    for relative in inputs:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / relative, path)
    (source / "scripts").mkdir(exist_ok=True)
    wheels = prefix / "wheels"
    wheels.mkdir(exist_ok=True)
    wheel_files = []
    for package_name in ("so101_quik", "so101_demo_py"):
        destination = wheels / package_name
        destination.mkdir()
        run([sys.executable, "setup.py", "bdist_wheel", "--dist-dir", str(destination)],
            prefix / "logs" / (package_name + "-build.log"), cwd=source / "src" / package_name, env=env)
        candidates = list(destination.glob("*.whl"))
        if len(candidates) != 1:
            raise ValueError("AMBIGUOUS_PACKAGE_WHEEL: " + package_name)
        wheel_files.extend(candidates)
        run([uv, "pip", "install", "--python", sys.executable, "--no-deps", str(candidates[0])],
            prefix / "logs" / (package_name + "-install.log"))
    run([uv, "pip", "check", "--python", sys.executable], prefix / "logs/dependency-check.log")
    verified = smoke(prefix, expected)
    # For an existing ROS workspace, build against its Python and use these headers.
    (prefix / "build-env.sh").write_text(
        "# Source before the normal ROS colcon build.\n"
        f"export Eigen3_DIR={shlex.quote(env['Eigen3_DIR'])}\n"
        f"export PATH={shlex.quote(str(prefix / 'env/bin'))}:\"$PATH\"\n")
    (prefix / "activate.sh").write_text(
        "# Standalone CPU IK environment; does not source a ROS installation.\n"
        f". {shlex.quote(str(prefix / 'env/bin/activate'))}\n"
        f". {shlex.quote(str(prefix / 'build-env.sh'))}\n")
    artifacts = dict(verified["artifacts"])
    import so101_demo
    import so101_quik
    for tree in (Path(so101_demo.__file__).parent, Path(so101_quik.__file__).parent,
                 prefix / "env/share/so101_demo_py", prefix / "env/share/so101_quik", eigen, eigen_install,
                 Path(so101_demo.__file__).parent.parent):
        artifacts.update({str(path): digest(path) for path in tree.rglob("*")
                          if path.is_file() and "__pycache__" not in path.parts})
    for path in (Path(args.base_python).resolve(), prefix / "bin/uv", eigen_archive,
                 eigen / "Eigen/Core", eigen / "Eigen/src/Core/util/Macros.h",
                 constraints, prefix / "activate.sh", prefix / "build-env.sh", Path(cmake), *wheel_files):
        artifacts[str(path)] = digest(path)
    try:
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        commit = None
    write_json(manifest, {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                         "source_commit": commit, "source_inputs": inputs,
                         "platform": platform.platform(), "machine": platform.machine(),
                         "python": sys.version, "python_executable": sys.executable,
                         "base_python": args.base_python, "index": args.index,
                         "compiler": subprocess.check_output([env["CXX"], "--version"], text=True),
                         **verified, "artifacts": artifacts})
    print("Both installed backends verified; manifest: " + str(manifest))


if __name__ == "__main__":
    main()
