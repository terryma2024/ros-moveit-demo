"""Head search sample camera and truth verification and the manifest check."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from so101_demo.act.head_camera_geometry.contract import scene_source_digests
from so101_demo.act.head_camera_geometry.validation import (
    camera_pose_from_seal,
    quaternion_wxyz_from_xyaxes,
)
from so101_demo.adapters.perception.mujoco_dataset.config import (
    DatasetConfig,
    geometry_seal_sha256,
    head_scenario_quotas,
)
from so101_demo.adapters.perception.mujoco_dataset.models import (
    HEAD_SEARCH_DATASET_CONTRACT,
    HEAD_SEARCH_SCENARIOS,
    RawRender,
)
from so101_demo.adapters.perception.mujoco_dataset.render import (
    _mask_sha256,
    decode_binary_mask_rle,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _head_profile_context(
    config: DatasetConfig, geometry_seal: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Refuse to render head-camera data unless the sealed production camera is the one in use."""

    if config.dataset_contract != HEAD_SEARCH_DATASET_CONTRACT:
        return None
    if geometry_seal is None:
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_REQUIRED: refusing to render head-camera data without the "
            "production-camera seal"
        )
    if config.geometry_seal is None or geometry_seal_sha256(geometry_seal) != (
        config.geometry_seal.accepted_seal_sha256
    ):
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_DRIFT: the supplied seal is not the accepted production-camera "
            "seal"
        )
    seal_camera = str(geometry_seal.get("camera_name", ""))
    if seal_camera != config.camera_name:
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_CAMERA_MISMATCH: the seal names camera "
            f"{seal_camera!r} but this dataset renders {config.camera_name!r}"
        )
    seal_sources = geometry_seal.get("source_digests") or {}
    scene_sources = scene_source_digests(config.mjcf_path)
    if seal_sources.get("camera_source_sha256") != scene_sources["camera_source_sha256"]:
        raise ValueError(
            "HEAD_DATASET_CAMERA_SOURCE_DRIFT: this dataset's scene includes a different camera "
            "source than the sealed production camera"
        )
    lock = [float(value) for value in geometry_seal.get("lock_valid_neck_rad") or []]
    if len(lock) != 2 or config.neck_yaw_rad is None:
        raise ValueError(
            "HEAD_DATASET_NECK_SAMPLING_REQUIRED: the head dataset needs both a sealed safe interval "
            "and a frozen neck-yaw sampling range"
        )
    low, high = config.neck_yaw_rad
    if low < lock[0] or high > lock[1]:
        raise ValueError(
            "HEAD_DATASET_NECK_SAMPLING_UNSAFE: the neck-yaw sampling range "
            f"[{low}, {high}] leaves the sealed safe interval {lock}"
        )
    sealed_camera = geometry_seal.get("camera")
    if not isinstance(sealed_camera, Mapping):
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_INCOMPLETE: the seal does not freeze the camera definition it "
            "accepted, so a render cannot be checked against it"
        )
    sealed_arm = geometry_seal.get("validation_arm_rad")
    if not isinstance(sealed_arm, (list, tuple)) or not sealed_arm:
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_INCOMPLETE: the seal does not freeze the arm pose its geometry "
            "was validated at"
        )
    if config.arm_pose_rad is None:
        raise ValueError(
            "HEAD_DATASET_ARM_POSE_UNDECLARED: the head profile must declare the arm configuration it "
            "renders from"
        )
    if len(config.arm_pose_rad) != len(sealed_arm) or any(
        not abs(observed - frozen) <= 1e-12
        for observed, frozen in zip(
            config.arm_pose_rad, [float(v) for v in sealed_arm], strict=True
        )
    ):
        raise ValueError(
            "HEAD_DATASET_ARM_POSE_DRIFT: the profile renders from an arm configuration the seal was "
            f"not validated at ({list(config.arm_pose_rad)} vs {list(sealed_arm)})"
        )
    if config.camera_jitter_m is None:
        raise ValueError(
            "HEAD_DATASET_CAMERA_JITTER_UNDECLARED: the head profile must declare its camera-mount "
            "jitter explicitly; inheriting the ordinary view jitter would move the sealed camera"
        )
    if any(float(value) != 0.0 for value in config.camera_jitter_m):
        raise ValueError(
            "HEAD_DATASET_CAMERA_JITTER_FORBIDDEN: the head profile renders the sealed camera and may "
            "not move it"
        )
    focal_px = (config.image_width / 2.0) / math.tan(
        float(geometry_seal["horizontal_fov_rad"]) / 2.0
    )
    return {
        "seal": geometry_seal,
        "seal_sha256": geometry_seal_sha256(geometry_seal),
        "focal_px": focal_px,
        "principal_point_px": (config.image_width / 2.0, config.image_height / 2.0),
        "camera": dict(sealed_camera),
        "arm_pose_rad": tuple(float(value) for value in sealed_arm),
    }


def _require_finite(name: str, values: object, size: int) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_IDENTITY_INVALID: {name} must be a {size}-element list"
        )
    numbers = [float(value) for value in values]
    if len(numbers) != size or any(not math.isfinite(value) for value in numbers):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_IDENTITY_INVALID: {name} must hold exactly {size} finite numbers"
        )
    return numbers


def _sample_camera_document(
    config: DatasetConfig, context: Mapping[str, Any], render: RawRender, scene_group_id: str
) -> dict[str, Any]:
    if render.camera_name != config.camera_name:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_MISSING: the render did not report the profile's camera "
            f"({render.camera_name!r} != {config.camera_name!r})"
        )
    if render.camera_position_m is None or render.camera_quaternion_wxyz is None:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_MISSING: the render did not report the camera's world pose"
        )
    if render.camera_local_position_m is None or render.camera_local_xyaxes is None:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_MISSING: the render did not report the camera's mounted pose"
        )
    if render.arm_pose_rad is None:
        raise ValueError(
            "HEAD_DATASET_ARM_POSE_MISSING: the render did not report the arm configuration it used"
        )
    sealed_arm = [float(value) for value in context["arm_pose_rad"]]
    observed_arm = [float(value) for value in render.arm_pose_rad]
    if len(observed_arm) != len(sealed_arm) or any(
        not abs(observed - frozen) <= 1e-12
        for observed, frozen in zip(observed_arm, sealed_arm, strict=True)
    ):
        raise ValueError(
            "HEAD_DATASET_ARM_POSE_DRIFT: the render used an arm configuration the seal was not "
            f"validated at ({observed_arm} vs {sealed_arm})"
        )
    sealed_fovy = float(context["camera"]["fovy_rad"])
    if (
        render.camera_fovy_rad is None
        or not abs(float(render.camera_fovy_rad) - sealed_fovy) <= 1e-9
    ):
        raise ValueError(
            "HEAD_DATASET_CAMERA_FOV_DRIFT: the render used a field of view the seal does not "
            f"describe ({render.camera_fovy_rad} vs {sealed_fovy})"
        )
    sealed = context["camera"]
    sealed_local = _require_finite("camera.local_position_m", sealed.get("local_position_m"), 3)
    sealed_axes = _require_finite("camera.local_xyaxes", sealed.get("local_xyaxes"), 6)
    observed_local = _require_finite("camera_local_position_m", render.camera_local_position_m, 3)
    observed_axes = _require_finite("camera_local_xyaxes", render.camera_local_xyaxes, 6)
    if any(
        abs(observed - frozen) > 1e-12
        for observed, frozen in zip(observed_local, sealed_local, strict=True)
    ) or any(
        abs(observed - frozen) > 1e-9
        for observed, frozen in zip(observed_axes, sealed_axes, strict=True)
    ):
        raise ValueError(
            "HEAD_DATASET_CAMERA_LOCAL_POSE_DRIFT: the render moved the camera inside its mount "
            f"({observed_local} vs the sealed {sealed_local}); the sealed geometry no longer describes "
            "these images"
        )
    for name, values in (
        ("camera_position_m", render.camera_position_m),
        ("camera_quaternion_wxyz", render.camera_quaternion_wxyz),
        ("camera_local_position_m", render.camera_local_position_m),
        ("camera_local_xyaxes", render.camera_local_xyaxes),
        ("arm_pose_rad", render.arm_pose_rad),
    ):
        numbers = [float(value) for value in values]
        if any(not math.isfinite(value) for value in numbers):
            raise ValueError(
                f"HEAD_DATASET_CAMERA_IDENTITY_INVALID: the render reports a non-finite {name}"
            )
    if not math.isfinite(float(render.neck_rad)):
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_INVALID: the render reports a non-finite neck angle"
        )
    observed_neck = float(render.neck_rad)
    low, high = (float(value) for value in config.neck_yaw_rad or ())
    if not low - 1e-9 <= observed_neck <= high + 1e-9:
        raise ValueError(
            "HEAD_DATASET_CAMERA_NECK_UNSAFE: the render used neck "
            f"{observed_neck}, outside the profile's declared range [{low}, {high}]"
        )
    lock = [float(value) for value in context["seal"].get("lock_valid_neck_rad") or []]
    if len(lock) != 2 or not lock[0] - 1e-9 <= observed_neck <= lock[1] + 1e-9:
        raise ValueError(
            "HEAD_DATASET_CAMERA_NECK_UNSAFE: the render used neck "
            f"{observed_neck}, outside the sealed safe interval {lock}"
        )
    quaternion_norm = math.sqrt(
        sum(float(value) * float(value) for value in render.camera_quaternion_wxyz)
    )
    if not abs(quaternion_norm - 1.0) <= 1e-6:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_INVALID: the render reports a non-unit orientation "
            f"(norm {quaternion_norm})"
        )
    predicted_position, predicted_axes = camera_pose_from_seal(
        context["seal"], float(render.neck_rad)
    )
    predicted_quaternion = quaternion_wxyz_from_xyaxes(predicted_axes)
    if any(
        not abs(observed - expected) <= 1e-6
        for observed, expected in zip(render.camera_position_m, predicted_position, strict=True)
    ):
        raise ValueError(
            "HEAD_DATASET_CAMERA_POSE_MISMATCH: the render's world position is not the pose the "
            "sealed mount model produces at this neck angle"
        )
    observed_quaternion = [float(value) for value in render.camera_quaternion_wxyz]
    direct = max(
        abs(observed - expected)
        for observed, expected in zip(observed_quaternion, predicted_quaternion, strict=True)
    )
    flipped = max(
        abs(observed + expected)
        for observed, expected in zip(observed_quaternion, predicted_quaternion, strict=True)
    )
    if min(direct, flipped) > 1e-6:
        raise ValueError(
            "HEAD_DATASET_CAMERA_POSE_MISMATCH: the render's orientation is not the pose the sealed "
            "mount model produces at this neck angle"
        )
    focal = float(context["focal_px"])
    cx, cy = (float(value) for value in context["principal_point_px"])
    return {
        "frame_id": render.camera_name,
        "width": config.image_width,
        "height": config.image_height,
        "k": [focal, 0.0, cx, 0.0, focal, cy, 0.0, 0.0, 1.0],
        "fovy_rad": sealed_fovy,
        "distortion": [float(value) for value in sealed["distortion"]],
        "distortion_model": str(sealed["distortion_model"]),
        "position_m": list(render.camera_position_m),
        "quaternion_wxyz": list(render.camera_quaternion_wxyz),
        "local_position_m": observed_local,
        "local_xyaxes": observed_axes,
        "neck_rad": render.neck_rad,
        "arm_rad": observed_arm,
        "scene_group_id": scene_group_id,
    }


def verify_head_search_manifest(
    manifest: Mapping[str, Any],
    *,
    dataset_root: Path,
    geometry_seal: Mapping[str, Any],
    expected_train: int,
    expected_val: int,
    expected_test: int,
    require_non_promotable: bool = False,
) -> dict[str, Any]:
    """Read one head-camera manifest back against its own files and the accepted seal.

    A manifest is a claim; this is the check that the claim is about the dataset on disk: exact
    counts, four balanced scenarios, one image per `scene_group_id`, a camera identity on every
    sample, every declared file present, and a promotion state that matches the profile it names.
    """

    if not isinstance(manifest, Mapping):
        raise ValueError("HEAD_DATASET_MANIFEST_INVALID: manifest must be a mapping")
    expected = {"train": expected_train, "val": expected_val, "test": expected_test}
    for value in expected.values():
        if type(value) is not int or value <= 0:
            raise ValueError(
                "HEAD_DATASET_EXPECTATION_INVALID: expected counts must be positive integers"
            )
    if manifest.get("dataset_contract") != HEAD_SEARCH_DATASET_CONTRACT:
        raise ValueError(
            "HEAD_DATASET_CONTRACT_INVALID: this is not a head search dataset manifest"
        )
    if manifest.get("camera_name") != geometry_seal.get("camera_name"):
        raise ValueError(
            "HEAD_DATASET_CAMERA_MISMATCH: the manifest names camera "
            f"{manifest.get('camera_name')!r} but the seal names {geometry_seal.get('camera_name')!r}"
        )
    if manifest.get("geometry_seal_sha256") != geometry_seal_sha256(geometry_seal):
        raise ValueError(
            "HEAD_DATASET_GEOMETRY_SEAL_DRIFT: the manifest was not produced under this seal"
        )
    raw_counts = manifest.get("split_counts") or {}
    split_counts = {split: int(raw_counts.get(split, 0)) for split in expected}
    if split_counts != expected:
        raise ValueError(
            f"HEAD_DATASET_COUNT_MISMATCH: the manifest holds {split_counts}, expected {expected}"
        )
    samples = list(manifest.get("samples") or [])
    if len(samples) != sum(expected.values()):
        raise ValueError(
            f"HEAD_DATASET_COUNT_MISMATCH: the manifest holds {len(samples)} samples, expected "
            f"{sum(expected.values())}"
        )
    sealed_camera = geometry_seal.get("camera")
    if not isinstance(sealed_camera, Mapping):
        raise ValueError(
            "HEAD_DATASET_GEOMETRY_SEAL_INCOMPLETE: the seal freezes no camera definition to check "
            "the samples against"
        )
    neck_range = [float(value) for value in manifest.get("neck_yaw_rad") or []]
    if len(neck_range) != 2:
        raise ValueError(
            "HEAD_DATASET_MANIFEST_INVALID: the manifest does not record the neck sampling range it "
            "was rendered with"
        )
    sealed_local = [float(value) for value in sealed_camera.get("local_position_m") or []]
    sealed_axes = [float(value) for value in sealed_camera.get("local_xyaxes") or []]
    if len(sealed_local) != 3 or len(sealed_axes) != 6:
        raise ValueError(
            "HEAD_DATASET_GEOMETRY_SEAL_INCOMPLETE: the seal's camera definition is not complete"
        )
    groups: dict[str, str] = {}
    scenario_counts: dict[str, Counter[str]] = {split: Counter() for split in expected}
    seen_paths: set[str] = set()
    seen_identities: set[tuple[int, int]] = set()
    root = Path(dataset_root)
    root_resolved = root.resolve()
    for sample in samples:
        split = str(sample.get("split"))
        if split not in expected:
            raise ValueError(f"HEAD_DATASET_SPLIT_INVALID: unknown split {split!r}")
        scenario = str(sample.get("scenario"))
        if scenario not in HEAD_SEARCH_SCENARIOS:
            raise ValueError(f"HEAD_DATASET_SCENARIO_INVALID: unknown scenario {scenario!r}")
        group = str(sample.get("scene_group_id") or "")
        if not group:
            raise ValueError(
                f"HEAD_DATASET_SCENE_GROUP_MISSING: seed {sample.get('seed')} declares no scene group"
            )
        camera = sample.get("camera") or {}
        _verify_sample_camera(camera, geometry_seal, sealed_local, sealed_axes, sample, neck_range)
        if group in groups:
            raise ValueError(
                f"HEAD_DATASET_SCENE_GROUP_DUPLICATE: {group} is claimed by more than one sample"
            )
        groups[group] = split
        scenario_counts[split][scenario] += 1
        for key in ("image", "label", "truth"):
            relative = sample.get(key)
            if not isinstance(relative, str) or not relative:
                raise ValueError(
                    f"HEAD_DATASET_FILE_MISSING: {key} of seed {sample.get('seed')} is not a path"
                )
            canonical = PurePosixPath(relative)
            if (
                canonical.is_absolute()
                or "\\" in relative
                or canonical.as_posix() != relative
                or any(part in {"", ".", ".."} for part in canonical.parts)
            ):
                raise ValueError(
                    f"HEAD_DATASET_FILE_PATH_INVALID: {relative!r} is not a canonical relative path"
                )
            candidate = root / relative
            if not candidate.is_file():
                raise ValueError(
                    f"HEAD_DATASET_FILE_MISSING: {key} {relative!r} of seed {sample.get('seed')} "
                    "is not on disk"
                )
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root_resolved):
                raise ValueError(
                    f"HEAD_DATASET_FILE_PATH_INVALID: {relative!r} resolves outside the dataset root "
                    "through a symlink"
                )
            if str(relative) in seen_paths:
                raise ValueError(
                    f"HEAD_DATASET_FILE_REUSED: {relative!r} is claimed by more than one sample"
                )
            seen_paths.add(str(relative))
            identity = resolved.stat()
            file_identity = (int(identity.st_dev), int(identity.st_ino))
            if file_identity in seen_identities:
                raise ValueError(
                    f"HEAD_DATASET_FILE_REUSED: {relative!r} is another sample's file under a "
                    "different path"
                )
            seen_identities.add(file_identity)
            digest = sample.get(f"{key}_sha256")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError(
                    f"HEAD_DATASET_FILE_DIGEST_MISSING: seed {sample.get('seed')} records no {key} "
                    "digest"
                )
            contents = (root / str(relative)).read_bytes()
            if hashlib.sha256(contents).hexdigest() != digest:
                raise ValueError(
                    f"HEAD_DATASET_FILE_DIGEST_MISMATCH: {relative!r} no longer matches the manifest"
                )
            if sample.get(f"{key}_bytes") != len(contents):
                raise ValueError(f"HEAD_DATASET_FILE_SIZE_MISMATCH: {relative!r} changed size")
        _verify_sample_truth(
            (root / str(sample["truth"])).read_text(encoding="utf-8"),
            sample,
            camera,
            group,
            split,
            image_shape_hw=(int(geometry_seal["image_height"]), int(geometry_seal["image_width"])),
        )
    for split, quota in head_scenario_quotas(expected).items():
        observed = dict(scenario_counts[split])
        if observed != quota:
            raise ValueError(
                f"HEAD_DATASET_SCENARIO_QUOTA_MISMATCH: {split} holds {observed}, expected {quota}"
            )
    for split, count in expected.items():
        images = sorted((root / "images" / split).glob("*.png"))
        labels = sorted((root / "labels" / split).glob("*.txt"))
        truths = sorted((root / "truth" / split).glob("*.json"))
        if not len(images) == len(labels) == len(truths) == count:
            raise ValueError(
                f"HEAD_DATASET_COUNT_MISMATCH: {split} holds {len(images)} images, {len(labels)} "
                f"labels and {len(truths)} truth files, expected {count} of each"
            )
    promotable = bool(manifest.get("promotable", False))
    if require_non_promotable and promotable:
        raise ValueError(
            "HEAD_DATASET_PROMOTABLE_FORBIDDEN: a smoke dataset must stay non-promotable"
        )
    if not require_non_promotable and not promotable:
        raise ValueError(
            "HEAD_DATASET_NOT_PROMOTABLE: this manifest is a smoke dataset and cannot satisfy the "
            "production contract"
        )
    return {
        "status": "OK",
        "sample_count": len(samples),
        "scene_group_count": len(groups),
        "split_counts": dict(split_counts),
        "scenario_counts": {split: dict(values) for split, values in scenario_counts.items()},
        "promotable": promotable,
        "geometry_seal_sha256": str(manifest.get("geometry_seal_sha256")),
    }


def _verify_sample_camera(
    camera: Mapping[str, Any],
    geometry_seal: Mapping[str, Any],
    sealed_local: list[float],
    sealed_axes: list[float],
    sample: Mapping[str, Any],
    neck_range: list[float],
) -> None:
    """Every sample must carry one complete, finite camera identity the seal predicts exactly."""

    seed = sample.get("seed")

    def invalid(reason: str) -> ValueError:
        return ValueError(f"HEAD_DATASET_CAMERA_IDENTITY_INVALID: seed {seed} {reason}")

    seal_camera_name = geometry_seal.get("camera_name")
    geometry_seal_camera = geometry_seal.get("camera") or {}
    if camera.get("frame_id") != seal_camera_name:
        raise invalid("names another camera")
    fields = {
        "k": 9,
        "distortion": 5,
        "position_m": 3,
        "quaternion_wxyz": 4,
        "local_position_m": 3,
        "local_xyaxes": 6,
        "arm_rad": 6,
    }
    observed: dict[str, list[float]] = {}
    for name, size in fields.items():
        values = camera.get(name)
        if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
            raise invalid(f"has no {name}")
        numbers = [float(value) for value in values]
        if len(numbers) != size or any(not math.isfinite(value) for value in numbers):
            raise invalid(f"has a non-finite or incomplete {name}")
        observed[name] = numbers
    neck = camera.get("neck_rad")
    if (
        isinstance(neck, bool)
        or not isinstance(neck, (int, float))
        or not math.isfinite(float(neck))
    ):
        raise invalid("has no finite neck angle")
    neck = float(neck)
    if camera.get("width") != geometry_seal.get("image_width") or camera.get(
        "height"
    ) != geometry_seal.get("image_height"):
        raise invalid("does not match the sealed image size")

    width = float(geometry_seal["image_width"])
    height = float(geometry_seal["image_height"])
    focal = (width / 2.0) / math.tan(float(geometry_seal["horizontal_fov_rad"]) / 2.0)
    if (
        not abs(
            float(camera.get("fovy_rad", float("nan"))) - float(geometry_seal_camera["fovy_rad"])
        )
        <= 1e-9
    ):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_FOV_DRIFT: seed {seed} reports a field of view the seal does not "
            "describe"
        )
    if camera.get("distortion_model") != geometry_seal_camera.get("distortion_model") or any(
        not abs(float(value) - float(frozen)) <= 1e-12
        for value, frozen in zip(
            camera.get("distortion") or [],
            geometry_seal_camera.get("distortion") or [],
            strict=False,
        )
    ):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_DISTORTION_DRIFT: seed {seed} reports a lens model the seal does not "
            "describe"
        )
    expected_k = [focal, 0.0, width / 2.0, 0.0, focal, height / 2.0, 0.0, 0.0, 1.0]
    if any(
        not abs(value - expected) <= 1e-6
        for value, expected in zip(observed["k"], expected_k, strict=True)
    ):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_INTRINSICS_MISMATCH: seed {seed} reports intrinsics the seal does "
            "not describe"
        )

    lock = [float(value) for value in geometry_seal.get("lock_valid_neck_rad") or []]
    if len(lock) != 2 or not lock[0] - 1e-9 <= neck <= lock[1] + 1e-9:
        raise ValueError(
            f"HEAD_DATASET_CAMERA_NECK_UNSAFE: seed {seed} was rendered at neck {neck}, outside the "
            f"sealed interval {lock}"
        )
    if not neck_range[0] - 1e-9 <= neck <= neck_range[1] + 1e-9:
        raise ValueError(
            f"HEAD_DATASET_CAMERA_NECK_UNSAFE: seed {seed} was rendered at neck {neck}, outside the "
            f"manifest's own sampling range {neck_range}"
        )

    expected_position, expected_axes = camera_pose_from_seal(geometry_seal, neck)
    if any(
        not abs(value - expected) <= 1e-6
        for value, expected in zip(observed["position_m"], expected_position, strict=True)
    ):
        raise ValueError(
            f"HEAD_DATASET_CAMERA_POSE_MISMATCH: seed {seed} reports a world pose the sealed mount "
            "model cannot produce"
        )
    expected_quaternion = quaternion_wxyz_from_xyaxes(expected_axes)
    quaternion = observed["quaternion_wxyz"]
    norm = math.sqrt(sum(value * value for value in quaternion))
    if not abs(norm - 1.0) <= 1e-6:
        raise ValueError(
            f"HEAD_DATASET_CAMERA_ORIENTATION_INVALID: seed {seed} reports a non-unit quaternion "
            f"(norm {norm})"
        )
    direct = max(
        abs(value - expected)
        for value, expected in zip(quaternion, expected_quaternion, strict=True)
    )
    flipped = max(
        abs(value + expected)
        for value, expected in zip(quaternion, expected_quaternion, strict=True)
    )
    if min(direct, flipped) > 1e-6:
        raise ValueError(
            f"HEAD_DATASET_CAMERA_POSE_MISMATCH: seed {seed} reports an orientation the sealed mount "
            "model cannot produce"
        )

    if any(
        not abs(value - frozen) <= 1e-12
        for value, frozen in zip(observed["local_position_m"], sealed_local, strict=True)
    ):
        raise invalid("was rendered from a camera position the seal does not describe")
    if any(
        not abs(value - frozen) <= 1e-9
        for value, frozen in zip(observed["local_xyaxes"], sealed_axes, strict=True)
    ):
        raise invalid("was rendered from a camera orientation the seal does not describe")
    sealed_arm = [float(value) for value in geometry_seal.get("validation_arm_rad") or []]
    if len(sealed_arm) != len(observed["arm_rad"]) or any(
        not abs(value - frozen) <= 1e-12
        for value, frozen in zip(observed["arm_rad"], sealed_arm, strict=True)
    ):
        raise ValueError(
            f"HEAD_DATASET_ARM_POSE_DRIFT: seed {seed} was rendered at an arm configuration the seal "
            "was not validated at"
        )


def _verify_sample_truth(
    contents: str,
    sample: Mapping[str, Any],
    camera: Mapping[str, Any],
    group: str,
    split: str,
    *,
    image_shape_hw: tuple[int, int],
) -> None:
    """The truth file must be about this sample, with the mask digests it claims."""

    try:
        truth = json.loads(contents)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} is not JSON"
        ) from error
    if not isinstance(truth, Mapping):
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} is not a mapping"
        )
    if (
        truth.get("scene_group_id") != group
        or truth.get("seed") != sample.get("seed")
        or truth.get("split") != split
    ):
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} describes "
            "another world state or split"
        )
    if dict(truth.get("camera") or {}) != dict(camera):
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} carries "
            "another camera identity"
        )
    instances = truth.get("instances")
    if not isinstance(instances, list):
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} lists no "
            "instances"
        )
    digests = []
    for instance in instances:
        if not isinstance(instance, Mapping):
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} has a "
                "malformed instance"
            )
        digest = instance.get("visible_mask_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: truth of seed {sample.get('seed')} records no "
                "raw mask digest"
            )
        try:
            mask = decode_binary_mask_rle(
                instance.get("visible_mask_rle_counts"), instance.get("mask_shape_hw")
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: the mask of seed {sample.get('seed')} does "
                f"not decode: {error}"
            ) from error
        if _mask_sha256(mask) != digest:
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: the stored mask of seed {sample.get('seed')} "
                "is not the mask its digest claims"
            )
        if tuple(instance.get("mask_shape_hw") or ()) != image_shape_hw:
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: the stored mask of seed {sample.get('seed')} "
                "is not shaped like the sealed image"
            )
        if instance.get("visible_pixel_count") != int(mask.sum()):
            raise ValueError(
                f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: the stored mask of seed {sample.get('seed')} "
                "does not hold the pixel count it claims"
            )
        digests.append(digest)
    aggregate = canonical_sha256(digests)
    if truth.get("raw_mask_sha256") != aggregate:
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: the raw mask digest of seed {sample.get('seed')} "
            "does not describe its own instances"
        )
    if sample.get("raw_mask_sha256") != aggregate:
        raise ValueError(
            f"HEAD_DATASET_TRUTH_IDENTITY_MISMATCH: seed {sample.get('seed')} records an aggregate "
            "mask digest its truth does not"
        )
