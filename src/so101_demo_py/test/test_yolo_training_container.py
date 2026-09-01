from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import yaml


PACKAGE_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = Path(__file__).parents[3]
RUNNER = REPOSITORY_ROOT / "scripts/yolo-seg-training-container.sh"
DOCKERFILE = (
    REPOSITORY_ROOT / "src/so101_demo_py/docker/yolo-training/Dockerfile"
)


def _write_fake_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _training_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    contract = tmp_path / "training.yaml"
    contract.write_text(
        yaml.safe_dump(
            {
                "task": "segment",
                "model": "yolo11n-seg.pt",
                "data": "dataset.yaml",
                "class_names": ["plastic_cup"],
                "classes": [0],
                "imgsz": 640,
                "epochs": 100,
                "device": "cuda",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    dataset_yaml = dataset_root / "dataset.yaml"
    dataset_yaml.write_text(
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: plastic_cup\n",
        encoding="utf-8",
    )
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"locked-local-model")
    return contract, dataset_yaml, base_model


def test_container_entrypoint_prepares_runtime_config_before_training(
    tmp_path: Path,
) -> None:
    """Catch bypassing prepare_training_run inside the training container."""
    contract, dataset_yaml, base_model = _training_inputs(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "yolo-args.txt"
    offline_capture = tmp_path / "offline.txt"
    _write_fake_executable(
        fake_bin / "yolo",
        'printf "%s\\n" "$@" > "$YOLO_ARGS_CAPTURE"\n'
        'printf "%s\\n" "${YOLO_OFFLINE:-}" > "$YOLO_OFFLINE_CAPTURE"',
    )
    output_root = tmp_path / "training-output" / "smoke"
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["PYTHONPATH"] = str(PACKAGE_ROOT)
    environment["YOLO_ARGS_CAPTURE"] = str(capture)
    environment["YOLO_OFFLINE_CAPTURE"] = str(offline_capture)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli.train_yolo_seg",
            "--contract",
            str(contract),
            "--dataset",
            str(dataset_yaml),
            "--base-model",
            str(base_model),
            "--output",
            str(output_root),
            "--run-name",
            "smoke",
            "--epochs",
            "1",
            "--fraction",
            "0.05",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=PACKAGE_ROOT,
    )

    assert result.returncode == 0, result.stderr
    runtime_config = output_root / "training-config.yaml"
    assert runtime_config.is_file()
    document = yaml.safe_load(runtime_config.read_text(encoding="utf-8"))
    assert document["model"] == str(base_model.resolve())
    assert document["data"] == str((output_root / "dataset.yaml").resolve())
    assert document["epochs"] == 1
    assert document["fraction"] == 0.05
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "segment",
        "train",
        f"cfg={runtime_config.resolve()}",
    ]
    assert offline_capture.read_text(encoding="utf-8").strip() == "true"


def test_host_runner_builds_the_repository_training_image(tmp_path: Path) -> None:
    """Catch building with the wrong Dockerfile or an incomplete context."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-build-args.txt"
    _write_fake_executable(
        fake_bin / "docker", 'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"'
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_ARGS_CAPTURE"] = str(capture)

    result = subprocess.run(
        [str(RUNNER), "build", "--image", "so101-yolo-train:test"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "build",
        "--platform",
        "linux/amd64",
        "--provenance=false",
        "--file",
        str(
            REPOSITORY_ROOT
            / "src/so101_demo_py/docker/yolo-training/Dockerfile"
        ),
        "--tag",
        "so101-yolo-train:test",
        str(REPOSITORY_ROOT),
    ]


def test_training_build_supports_explicit_refresh_and_external_cache(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-build-args.txt"
    _write_fake_executable(
        fake_bin / "docker", 'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"'
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_ARGS_CAPTURE"] = str(capture)

    result = subprocess.run(
        [
            str(RUNNER),
            "build",
            "--refresh-base",
            "--cache-from",
            "type=local,src=/tmp/so101-cache",
            "--cache-to",
            "type=local,dest=/tmp/so101-cache,mode=max",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    assert arguments[:4] == ["buildx", "build", "--load", "--pull"]
    assert ["--cache-from", "type=local,src=/tmp/so101-cache"] == arguments[
        arguments.index("--cache-from") : arguments.index("--cache-from") + 2
    ]
    assert ["--cache-to", "type=local,dest=/tmp/so101-cache,mode=max"] == arguments[
        arguments.index("--cache-to") : arguments.index("--cache-to") + 2
    ]


def test_training_image_uses_tsinghua_for_python_packages() -> None:
    """Catch sending ordinary Python packages back through the slower default index."""
    contents = DOCKERFILE.read_text(encoding="utf-8")

    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in contents
    assert "https://download.pytorch.org/whl/cu130" in contents


def test_host_runner_mounts_inputs_read_only_and_output_read_write(
    tmp_path: Path,
) -> None:
    """Catch mutable training inputs or an output path trapped in the container."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-run-args.txt"
    _write_fake_executable(
        fake_bin / "docker", 'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"'
    )
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    dataset_yaml = dataset_root / "dataset.yaml"
    dataset_yaml.write_text("names:\n  0: plastic_cup\n", encoding="utf-8")
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"locked-local-model")
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    output_root = output_parent / "smoke-001"
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_ARGS_CAPTURE"] = str(capture)

    result = subprocess.run(
        [
            str(RUNNER),
            "train",
            "--image",
            "so101-yolo-train:test",
            "--dataset",
            str(dataset_yaml),
            "--model",
            str(base_model),
            "--output",
            str(output_root),
            "--run-name",
            "smoke",
            "--epochs",
            "1",
            "--fraction",
            "0.05",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    assert arguments[:12] == [
        "run",
        "--rm",
        "--gpus",
        "all",
        "--network",
        "none",
        "--shm-size",
        "8g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "YOLO_OFFLINE=true",
    ]
    assert (
        f"type=bind,src={dataset_root.resolve()},dst=/dataset,readonly" in arguments
    )
    assert (
        f"type=bind,src={base_model.resolve()},dst=/models/yolo11n-seg.pt,readonly"
        in arguments
    )
    assert (
        f"type=bind,src={output_parent.resolve()},dst=/training-output" in arguments
    )
    assert arguments[-15:] == [
        "so101-yolo-train:test",
        "--contract",
        "/opt/so101_demo_py/config/perception/training.yaml",
        "--dataset",
        "/dataset/dataset.yaml",
        "--base-model",
        "/models/yolo11n-seg.pt",
        "--output",
        "/training-output/smoke-001",
        "--run-name",
        "smoke",
        "--epochs",
        "1",
        "--fraction",
        "0.05",
    ]
