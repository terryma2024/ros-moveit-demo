from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
RUNNER = REPOSITORY_ROOT / "scripts/yolo-seg-inference-container.sh"
DOCKERFILE = (
    REPOSITORY_ROOT / "src/so101_demo_py/docker/yolo-inference/Dockerfile"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_build_uses_the_pinned_inference_dockerfile_and_amd64_platform(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-build-args.txt"
    _write_executable(
        fake_bin / "docker",
        'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"',
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_ARGS_CAPTURE": str(capture),
    }

    completed = subprocess.run(
        [str(RUNNER), "build", "--image", "registry.example/so101-yolo:locked"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "build",
        "--platform",
        "linux/amd64",
        "--provenance=false",
        "--file",
        str(DOCKERFILE),
        "--tag",
        "registry.example/so101-yolo:locked",
        str(REPOSITORY_ROOT),
    ]


def test_build_refreshes_the_pinned_base_only_when_requested(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-build-args.txt"
    _write_executable(
        fake_bin / "docker",
        'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"',
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_ARGS_CAPTURE": str(capture),
    }

    completed = subprocess.run(
        [str(RUNNER), "build", "--refresh-base"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    assert arguments[0] == "build"
    assert arguments.count("--pull") == 1


def test_build_uses_buildx_only_when_external_cache_is_requested(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-build-args.txt"
    _write_executable(
        fake_bin / "docker",
        'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"',
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_ARGS_CAPTURE": str(capture),
    }

    completed = subprocess.run(
        [
            str(RUNNER),
            "build",
            "--cache-from",
            "type=registry,ref=registry.example/so101/cache:main",
            "--cache-to",
            "type=registry,ref=registry.example/so101/cache:main,mode=max",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "buildx",
        "build",
        "--load",
        "--platform",
        "linux/amd64",
        "--provenance=false",
        "--file",
        str(DOCKERFILE),
        "--tag",
        "so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115",
        "--cache-from",
        "type=registry,ref=registry.example/so101/cache:main",
        "--cache-to",
        "type=registry,ref=registry.example/so101/cache:main,mode=max",
        str(REPOSITORY_ROOT),
    ]
