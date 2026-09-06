from __future__ import annotations

import os
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = Path(__file__).parents[3]
RUNNER = REPOSITORY_ROOT / "scripts/grounding-dino-training-container.sh"
DOCKERFILE = REPOSITORY_ROOT / "src/so101_demo_py/docker/grounding-dino-training/Dockerfile"
TRAINING_CONFIG = PACKAGE_ROOT / "config/perception/grounding_dino_training.yaml"
DOMAIN_RETENTION_CONFIG = (
    PACKAGE_ROOT / "config/perception/grounding_dino_domain_retention_training.yaml"
)
DOMAIN_RETENTION_LAST_STAGE_CONFIG = (
    PACKAGE_ROOT / "config/perception/grounding_dino_domain_retention_last_stage_training.yaml"
)


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


def _domain_retention_inputs(tmp_path: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for split in ("train", "real-val", "near-val"):
        key = split.replace("-", "_")
        image_root = tmp_path / f"{split}-images"
        image_root.mkdir()
        result[f"{key}_images"] = image_root
        inventory = tmp_path / f"{split}-inventory.json"
        inventory.write_text("{}\n", encoding="utf-8")
        result[f"{key}_inventory"] = inventory
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


def test_domain_retention_mounts_only_three_allowed_splits_and_official_base(
    tmp_path: Path,
) -> None:
    inputs = _domain_retention_inputs(tmp_path)
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
            "domain-retention",
            "--image",
            "so101-grounding-dino:test",
            "--train-images",
            str(inputs["train_images"]),
            "--real-val-images",
            str(inputs["real_val_images"]),
            "--near-val-images",
            str(inputs["near_val_images"]),
            "--train-inventory",
            str(inputs["train_inventory"]),
            "--real-val-inventory",
            str(inputs["real_val_inventory"]),
            "--near-val-inventory",
            str(inputs["near_val_inventory"]),
            "--base-model",
            str(inputs["model"]),
            "--output",
            str(inputs["output"]),
            "--mode",
            "smoke",
            "--training-commit",
            "2" * 40,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    expected_mounts = {
        f"type=bind,src={inputs['train_images'].resolve()},dst=/images/train,readonly",
        f"type=bind,src={inputs['real_val_images'].resolve()},dst=/images/real-val,readonly",
        f"type=bind,src={inputs['near_val_images'].resolve()},dst=/images/near-val,readonly",
        f"type=bind,src={inputs['train_inventory'].resolve()},dst=/inventories/train.json,readonly",
        f"type=bind,src={inputs['real_val_inventory'].resolve()},dst=/inventories/real-val.json,readonly",
        f"type=bind,src={inputs['near_val_inventory'].resolve()},dst=/inventories/near-val.json,readonly",
        f"type=bind,src={inputs['model'].resolve()},dst=/models/grounding-dino-tiny,readonly",
        f"type=bind,src={inputs['output'].parent.resolve()},dst=/training-output",
    }
    mounts = {
        arguments[index + 1] for index, value in enumerate(arguments[:-1]) if value == "--mount"
    }
    assert mounts == expected_mounts
    image_index = arguments.index("so101-grounding-dino:test")
    assert arguments[image_index - 2 : image_index] == [
        "--entrypoint",
        "train_grounding_dino_domain_retention",
    ]
    assert arguments[image_index + 1 :] == [
        "--contract",
        "/opt/so101_demo_py/config/perception/grounding_dino_domain_retention_training.yaml",
        "--train-inventory",
        "/inventories/train.json",
        "--real-val-inventory",
        "/inventories/real-val.json",
        "--near-val-inventory",
        "/inventories/near-val.json",
        "--train-images",
        "/images/train",
        "--real-val-images",
        "/images/real-val",
        "--near-val-images",
        "/images/near-val",
        "--base-model",
        "/models/grounding-dino-tiny",
        "--output",
        "/training-output/smoke-r1",
        "--mode",
        "smoke",
        "--training-commit",
        "2" * 40,
    ]
    joined = "\n".join(arguments).lower()
    assert "coco100" not in joined
    assert "sam2" not in joined
    assert "test-sealed-members" not in joined


def test_domain_retention_last_stage_mounts_selected_phase1_student_read_only(
    tmp_path: Path,
) -> None:
    inputs = _domain_retention_inputs(tmp_path)
    student = tmp_path / "selected-phase1-epoch-002"
    student.mkdir()
    (student / "checkpoint-manifest.json").write_text("{}\n", encoding="utf-8")
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
            "domain-retention",
            "--image",
            "so101-grounding-dino:test",
            "--train-images",
            str(inputs["train_images"]),
            "--real-val-images",
            str(inputs["real_val_images"]),
            "--near-val-images",
            str(inputs["near_val_images"]),
            "--train-inventory",
            str(inputs["train_inventory"]),
            "--real-val-inventory",
            str(inputs["real_val_inventory"]),
            "--near-val-inventory",
            str(inputs["near_val_inventory"]),
            "--base-model",
            str(inputs["model"]),
            "--student-model",
            str(student),
            "--output",
            str(inputs["output"]),
            "--mode",
            "smoke",
            "--training-commit",
            "3" * 40,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    arguments = capture.read_text(encoding="utf-8").splitlines()
    mounts = {
        arguments[index + 1] for index, value in enumerate(arguments[:-1]) if value == "--mount"
    }
    assert (
        f"type=bind,src={student.resolve()},dst=/models/student-initialization,readonly"
        in mounts
    )
    image_index = arguments.index("so101-grounding-dino:test")
    assert arguments[image_index + 1 : image_index + 3] == [
        "--contract",
        "/opt/so101_demo_py/config/perception/grounding_dino_domain_retention_last_stage_training.yaml",
    ]
    assert arguments[-2:] == ["--student-model", "/models/student-initialization"]
    joined = "\n".join(arguments).lower()
    assert "epoch-005" not in joined and "coco100" not in joined and "sam2" not in joined


def test_dockerfile_pins_locked_cuda_torch_and_transformers() -> None:
    contents = DOCKERFILE.read_text(encoding="utf-8")

    assert "13.0.2-cudnn-runtime-ubuntu24.04@sha256:" in contents
    assert "torch==2.13.0+cu130" in contents
    assert "torchvision==0.28.0+cu130" in contents
    assert "transformers==4.56.2" in contents
    assert 'ENTRYPOINT ["train_grounding_dino"]' in contents


def test_training_contract_records_the_cuda_determinism_exception() -> None:
    contents = TRAINING_CONFIG.read_text(encoding="utf-8")

    assert "  deterministic_algorithms: true\n" in contents
    assert "  deterministic_warn_only: true\n" in contents
    assert "  cudnn_benchmark: false\n" in contents
    assert "  cudnn_deterministic: true\n" in contents
    assert "  disable_flash_sdp: true\n" in contents
    assert "  disable_memory_efficient_sdp: true\n" in contents


def test_domain_retention_contract_is_packaged_and_has_no_resume() -> None:
    contents = DOMAIN_RETENTION_CONFIG.read_text(encoding="utf-8")

    assert "  initialization: official_base_teacher_and_student\n" in contents
    assert "  resume_checkpoint: null\n" in contents
    assert "  teacher_token_logit_lambda: 1.0\n" in contents
    assert "  teacher_candidate_box_lambda: 1.0\n" in contents
    assert (
        "  source_archive_sha256: "
        "6479714bd350dc3460ec2b26e9b683bf608bd24ac6c7b159c95d5fea754fa2db\n"
        in contents
    )
    assert (
        "  train_inventory_sha256: "
        "4f32d9f7e780baacffb4134b557f64f8b510eaa38ba984e2f0a5f4466c74442a\n"
        in contents
    )
    assert (
        "  val_inventory_sha256: "
        "9db4e3a6db44e0e2c690af4cd959d1019c46e352f874d8a4b32ce70bc56e7572\n"
        in contents
    )


def test_last_stage_contract_pins_parent_and_one_tenth_backbone_lr() -> None:
    contents = DOMAIN_RETENTION_LAST_STAGE_CONFIG.read_text(encoding="utf-8")

    assert "  initialization: selected_phase1_student_official_base_teacher\n" in contents
    assert "  resume_checkpoint: null\n" in contents
    assert "  backbone_learning_rate: 0.0000002\n" in contents
    assert (
        "  student_initialization_checkpoint_manifest_sha256: "
        "8b511bbed06f6b950ab74a6010a3c61d8e55b9d8b9ab760435a2fb1b09423f7f\n"
        in contents
    )
    assert (
        "  student_initialization_model_sha256: "
        "1c302e9b14364e2b57e75ca409b3238d8ec6ac46bc59931f9f4acdae4005abb5\n"
        in contents
    )
    assert "  student_initialization_completed_epoch: 3\n" in contents
    assert (
        "  source_archive_sha256: "
        "6479714bd350dc3460ec2b26e9b683bf608bd24ac6c7b159c95d5fea754fa2db\n"
        in contents
    )
    assert (
        "  train_inventory_sha256: "
        "4f32d9f7e780baacffb4134b557f64f8b510eaa38ba984e2f0a5f4466c74442a\n"
        in contents
    )
    assert (
        "  val_inventory_sha256: "
        "9db4e3a6db44e0e2c690af4cd959d1019c46e352f874d8a4b32ce70bc56e7572\n"
        in contents
    )
