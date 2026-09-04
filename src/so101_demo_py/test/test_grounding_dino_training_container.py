from __future__ import annotations

import os
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = Path(__file__).parents[3]
RUNNER = REPOSITORY_ROOT / "scripts/grounding-dino-training-container.sh"
DOCKERFILE = REPOSITORY_ROOT / "src/so101_demo_py/docker/grounding-dino-training/Dockerfile"


def _write_fake_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _inputs(tmp_path: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for split in ("train", "val"):
        image_root = tmp_path / f"{split}-images"
        image_root.mkdir()
        result[f"{split}_images"] = image_root
        inventory = tmp_path / f"{split}-inventory.json"
        inventory.write_text("{}\n", encoding="utf-8")
        result[f"{split}_inventory"] = inventory
    model = tmp_path / "grounding-dino-tiny"
    model.mkdir()
    (model / "config.json").write_text("{}\n", encoding="utf-8")
    result["model"] = model
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    result["output"] = output_parent / "smoke-r1"
    return result


def test_host_runner_builds_the_independent_pinned_training_image(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-args.txt"
    _write_fake_executable(fake_bin / "docker", 'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"')
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_ARGS_CAPTURE"] = str(capture)

    result = subprocess.run(
        [str(RUNNER), "build", "--image", "so101-grounding-dino:test"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    assert arguments == [
        "build",
        "--platform",
        "linux/amd64",
        "--provenance=false",
        "--file",
        str(DOCKERFILE),
        "--tag",
        "so101-grounding-dino:test",
        str(REPOSITORY_ROOT),
    ]


def test_train_mounts_only_train_val_and_model_read_only(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-args.txt"
    _write_fake_executable(fake_bin / "docker", 'printf "%s\\n" "$@" > "$DOCKER_ARGS_CAPTURE"')
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_ARGS_CAPTURE"] = str(capture)

    result = subprocess.run(
        [
            str(RUNNER),
            "train",
            "--image",
            "so101-grounding-dino:test",
            "--train-images",
            str(inputs["train_images"]),
            "--val-images",
            str(inputs["val_images"]),
            "--train-inventory",
            str(inputs["train_inventory"]),
            "--val-inventory",
            str(inputs["val_inventory"]),
            "--base-model",
            str(inputs["model"]),
            "--output",
            str(inputs["output"]),
            "--mode",
            "smoke",
            "--training-commit",
            "1" * 40,
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
        "HF_HUB_OFFLINE=1",
    ]
    expected_mounts = {
        f"type=bind,src={inputs['train_images'].resolve()},dst=/images/train,readonly",
        f"type=bind,src={inputs['val_images'].resolve()},dst=/images/val,readonly",
        f"type=bind,src={inputs['train_inventory'].resolve()},dst=/inventories/train.json,readonly",
        f"type=bind,src={inputs['val_inventory'].resolve()},dst=/inventories/val.json,readonly",
        f"type=bind,src={inputs['model'].resolve()},dst=/models/grounding-dino-tiny,readonly",
        f"type=bind,src={inputs['output'].parent.resolve()},dst=/training-output",
    }
    mounts = {
        arguments[index + 1] for index, value in enumerate(arguments[:-1]) if value == "--mount"
    }
    assert mounts == expected_mounts
    joined = "\n".join(arguments).lower()
    assert "test-sealed-members" not in joined
    assert "images/test" not in joined
    assert "coco100" not in joined
    assert "sam2" not in joined
    assert (
        arguments[-15:]
        == [
            "so101-grounding-dino:test",
            "--contract",
            "/opt/so101_demo_py/config/perception/grounding_dino_training.yaml",
            "--train-inventory",
            "/inventories/train.json",
            "--val-inventory",
            "/inventories/val.json",
            "--train-images",
            "/images/train",
            "--val-images",
            "/images/val",
            "--base-model",
            "/models/grounding-dino-tiny",
            "--output",
            "/training-output/smoke-r1",
            "--mode",
            "smoke",
            "--training-commit",
            "1" * 40,
        ][-15:]
    )


def test_runner_rejects_output_collision_before_docker(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs["output"].mkdir()

    result = subprocess.run(
        [
            str(RUNNER),
            "train",
            "--train-images",
            str(inputs["train_images"]),
            "--val-images",
            str(inputs["val_images"]),
            "--train-inventory",
            str(inputs["train_inventory"]),
            "--val-inventory",
            str(inputs["val_inventory"]),
            "--base-model",
            str(inputs["model"]),
            "--output",
            str(inputs["output"]),
            "--mode",
            "smoke",
            "--training-commit",
            "1" * 40,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "already exists" in result.stderr


def test_dockerfile_pins_locked_cuda_torch_and_transformers() -> None:
    contents = DOCKERFILE.read_text(encoding="utf-8")

    assert "13.0.2-cudnn-runtime-ubuntu24.04@sha256:" in contents
    assert "torch==2.13.0+cu130" in contents
    assert "torchvision==0.28.0+cu130" in contents
    assert "transformers==4.56.2" in contents
    assert 'ENTRYPOINT ["train_grounding_dino"]' in contents
