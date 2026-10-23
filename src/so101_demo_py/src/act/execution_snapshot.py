"""Byte-bound execution inputs, including the MuJoCo asset tree and recipe targets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .qc_session import session_memo
from .rig_files import KNOWN_SCENES, rig_for_scene, rig_model_files

KIND = "ACT_DIAGNOSTIC_EPISODE_EXECUTION_INPUTS"
#: the head+wrist rig's scene, the default; a snapshot records the scene of its rig in `scene_path` (`rig_files`)
SCENE = "assets/mujoco/act/scene.xml"
MOTION = "config/policies/dynamic_cup_pick/mujoco.yaml"
_FIELDS = frozenset({"kind", "schema_version", "files", "source_files", "source_sha256",
                     "scene_path", "motion_policy_path", "model_sha256", "mujoco_version",
                     "nq", "nv", "targets", "snapshot_sha256"})
_SOURCE_ROOTS = (
    "src/so101_demo_py/src", "src/so101_demo_py/config", "src/so101_demo_py/launch",
    "src/so101_teleop/so101_teleop", "src/so101_teleop/launch",
    "src/so101_mujoco_support/src", "src/so101_mujoco_support/include",
    "src/so101_mujoco_support/msg",
    "third_party/mujoco_ros2_control/mujoco_ros2_control/src",
    "third_party/mujoco_ros2_control/mujoco_ros2_control/include",
    "third_party/mujoco_ros2_control/mujoco_ros2_control_msgs",
    # the lossless queued-state controller overlay that replaces the apt controllers
    "third_party/ros2_controllers/joint_trajectory_controller/src",
    "third_party/ros2_controllers/joint_trajectory_controller/include",
    "third_party/ros2_controllers/joint_state_broadcaster/src",
    "third_party/ros2_controllers/joint_state_broadcaster/include",
    "third_party/ros2_controllers/so101_queued_state_publisher/include",
)
_SOURCE_SUFFIXES = {".py", ".cpp", ".hpp", ".h", ".yaml", ".json", ".xml", ".srdf", ".msg", ".srv", ".action"}


def verify_installed_station_assets(share: Path, snapshot: dict) -> None:
    """Bind the ACT launch's installed model/config bytes of the snapshot's rig to the frozen inputs."""
    rig = rig_for_scene(snapshot["scene_path"])
    required = {
        rig.urdf, "assets/common/geometry-manifest.yaml", rig.controllers, rig.plugins,
        "config/mujoco/moveit_controllers.yaml", "config/mujoco/so101.srdf",
        "config/mujoco/kinematics.yaml", "config/mujoco/joint_limits.yaml",
        "config/mujoco/ompl_planning.yaml",
    }
    expected = {relative: snapshot["files"].get(relative) for relative in required}
    # The installed URDF uses package:// common meshes while MuJoCo uses its
    # frozen literal mesh paths. Check both consumers of the same source assets.
    prefix = "src/so101_demo_py/"
    for relative, metadata in snapshot["source_files"].items():
        if relative.startswith(prefix + "assets/common/"):
            expected[relative.removeprefix(prefix)] = metadata
    for relative, metadata in snapshot["files"].items():
        if relative.startswith(("assets/mujoco/assets/", "assets/mujoco/collision/")):
            expected[relative] = metadata
    for relative, metadata in sorted(expected.items()):
        try:
            payload = (Path(share) / relative).read_bytes()
        except OSError as error:
            raise ValueError("EPISODE_INSTALLED_ASSET_MISMATCH: " + relative) from error
        if metadata is None or _metadata(payload) != metadata:
            raise ValueError("EPISODE_INSTALLED_ASSET_MISMATCH: " + relative)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _metadata(payload: bytes) -> dict:
    return {"sha256": _sha(payload), "bytes": len(payload)}


def _regular(path: Path, root: Path) -> bytes:
    # Every component is checked; a regular leaf through a symlinked directory is also refused.
    if not path.is_relative_to(root) or any(part.is_symlink() for part in
                                           (path, *path.parents) if part.is_relative_to(root)):
        raise ValueError("EXECUTION_SNAPSHOT_PATH_INVALID")
    if not path.is_file():
        raise ValueError("EXECUTION_SNAPSHOT_FILE_MISSING")
    return path.read_bytes()


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _model_and_targets(root: Path, scene: str = SCENE) -> dict:
    import mujoco
    from ..adapters.act.physics import model_sha256
    from ..core.dynamic_pick import compose_pose, inverse_pose
    from ..core.dynamic_pick_policy import load_dynamic_policy_variant

    model = mujoco.MjModel.from_xml_path(str(root / scene))
    template = load_dynamic_policy_variant(root, backend="mujoco").template
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "task_start")
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, template.object_id)
    if key < 0 or body < 0 or template.planning_frame != "world":
        raise ValueError("EXECUTION_SNAPSHOT_RECIPE_INVALID")
    # Compile and evaluate the frozen reset keyframe only. No simulation stepping or runtime is started.
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, key)
    mujoco.mj_forward(model, data)
    w, x, y, z = data.xquat[body]
    initial = [*map(float, data.xpos[body]), float(x), float(y), float(z), float(w)]
    final = list(compose_pose(template.place_tcp_world, inverse_pose(template.cup_to_tcp_grasp)).values)
    transform = list(template.cup_to_tcp_grasp.values)
    return {"model_sha256": model_sha256(model), "mujoco_version": mujoco.__version__,
            "nq": model.nq, "nv": model.nv,
            "targets": {"kind": "ACT_ENDPOINT_TARGETS", "schema_version": 1,
                        "object_id": template.object_id, "body_name": template.object_id,
                        "frame_id": "world", "reset_keyframe": "task_start",
                        "initial_target": initial, "final_target": final,
                        "reset_recipe_sha256": _sha((root / scene).read_bytes()),
                        "place_recipe_sha256": _sha((root / MOTION).read_bytes()),
                        "cup_to_tcp_xyz_xyzw": transform,
                        "transform_sha256": _sha(_canonical(transform))}}


def freeze_execution_snapshot(source_root: Path, output: Path, rig=None) -> dict:
    """Freeze the actual package source, full model assets and approved motion recipe once.

    `rig` (a profile, a rig name or None for the head+wrist default) names the scene the snapshot is recorded against."""
    scene = rig_model_files(rig).scene
    source = Path(source_root).resolve()
    target = Path(output)
    if target.exists() or target.is_symlink():
        raise ValueError("EXECUTION_SNAPSHOT_EXISTS")
    package = source / "src/so101_demo_py"
    from ..core.dynamic_pick_policy import load_dynamic_policy_variant
    # This checks the controlled manifest's approved variant digest before copying any inputs.
    load_dynamic_policy_variant(package, backend="mujoco")
    payloads, source_files = {}, {}
    for relative_root in _SOURCE_ROOTS:
        tree = source / relative_root
        if not tree.is_dir() or tree.is_symlink():
            raise ValueError("EXECUTION_SNAPSHOT_SOURCE_MISSING: " + relative_root)
        for path in sorted(tree.rglob("*")):
            if path.is_file() and path.suffix in _SOURCE_SUFFIXES:
                relative = path.relative_to(source).as_posix()
                payload = _regular(path, source)
                source_files[relative] = _metadata(payload)
                payloads["source/" + relative] = payload
    for path in sorted((package / "assets/mujoco").rglob("*")):
        if path.is_file():
            # The controlled model assets use repository-local mesh symlinks. Freeze their
            # resolved bytes as regular files at the model's literal relative path; never
            # preserve a link into a mutable source tree or accept a target outside assets.
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(package / "assets"):
                raise ValueError("EXECUTION_SNAPSHOT_ASSET_ESCAPE")
            payload = _regular(resolved, source)
            payloads[path.relative_to(package).as_posix()] = payload
            relative = resolved.relative_to(source).as_posix()
            source_files[relative] = _metadata(payload)
            payloads["source/" + relative] = payload
    geometry_path = package / "assets/common/geometry-manifest.yaml"
    payloads["assets/common/geometry-manifest.yaml"] = _regular(geometry_path, source)
    source_files[geometry_path.relative_to(source).as_posix()] = _metadata(payloads["assets/common/geometry-manifest.yaml"])
    payloads["source/" + geometry_path.relative_to(source).as_posix()] = payloads["assets/common/geometry-manifest.yaml"]
    for path in sorted((package / "config").rglob("*")):
        if path.is_file() and path.suffix in _SOURCE_SUFFIXES:
            payloads[path.relative_to(package).as_posix()] = _regular(path, source)
    for package_path in ("src/so101_demo_py", "src/so101_teleop", "src/so101_mujoco_support",
                         "third_party/mujoco_ros2_control/mujoco_ros2_control",
                         "third_party/mujoco_ros2_control/mujoco_ros2_control_msgs",
                         "third_party/ros2_controllers/joint_trajectory_controller",
                         "third_party/ros2_controllers/joint_state_broadcaster",
                         "third_party/ros2_controllers/so101_queued_state_publisher"):
        for filename in ("package.xml", "CMakeLists.txt", "setup.py", "setup.cfg"):
            path = source / package_path / filename
            if path.is_file():
                relative = path.relative_to(source).as_posix()
                payload = _regular(path, source)
                source_files[relative] = _metadata(payload)
                payloads["source/" + relative] = payload
    payloads[MOTION] = _regular(package / MOTION, source)
    target.mkdir(parents=True)
    for relative, payload in payloads.items():
        _write_new(target / relative, payload)
    descriptor = {"kind": KIND, "schema_version": 1,
                  "files": {path: _metadata(payload) for path, payload in sorted(payloads.items())},
                  "source_files": source_files,
                  "source_sha256": _sha(_canonical({"kind": "ACT_DIAGNOSTIC_EPISODE_SOURCE",
                                                    "schema_version": 1, "files": source_files})),
                  "scene_path": scene, "motion_policy_path": MOTION,
                  **_model_and_targets(target, scene)}
    descriptor["snapshot_sha256"] = _sha(_canonical(descriptor))
    _write_new(target / "execution-manifest.json", _canonical(descriptor))
    # Persist the nested directory entries, not only their files and the top-level manifest.
    directories = [target, *(path for path in target.rglob("*") if path.is_dir())]
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        descriptor_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor_fd)
        finally:
            os.close(descriptor_fd)
    parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return verify_execution_snapshot(target)


def _snapshot_key(root: Path, *, expected_sha256: str | None = None) -> tuple:
    from .qc_session import tree_signature

    root = Path(root).absolute()
    return str(root), expected_sha256, tree_signature(root)


@session_memo(_snapshot_key)
def verify_execution_snapshot(root: Path, *, expected_sha256: str | None = None) -> dict:
    """Verify the retained bytes and independently recompute the frozen recipe targets."""
    root = Path(root).absolute()
    try:
        document = json.loads(_regular(root / "execution-manifest.json", root))
        if (not isinstance(document, dict) or set(document) != _FIELDS or document["kind"] != KIND
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or document["scene_path"] not in KNOWN_SCENES or document["motion_policy_path"] != MOTION):
            raise ValueError("EXECUTION_SNAPSHOT_SCHEMA_INVALID")
        digest = _sha(_canonical({key: value for key, value in document.items() if key != "snapshot_sha256"}))
        if digest != document["snapshot_sha256"] or (expected_sha256 is not None and digest != expected_sha256):
            raise ValueError("EXECUTION_SNAPSHOT_HASH_INVALID")
        files, source_files = document["files"], document["source_files"]
        if not isinstance(files, dict) or not files or not isinstance(source_files, dict) or not source_files:
            raise ValueError("EXECUTION_SNAPSHOT_SCHEMA_INVALID")
        for relative, metadata in files.items():
            path = Path(relative)
            if (not isinstance(relative, str) or path.is_absolute() or ".." in path.parts
                    or not path.parts or not isinstance(metadata, dict) or set(metadata) != {"sha256", "bytes"}
                    or type(metadata["bytes"]) is not int or metadata["bytes"] < 0):
                raise ValueError("EXECUTION_SNAPSHOT_SCHEMA_INVALID")
            if _metadata(_regular(root / path, root)) != metadata:
                raise ValueError("EXECUTION_SNAPSHOT_BYTES_INVALID: " + relative)
        actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
        if actual != set(files) | {"execution-manifest.json"}:
            raise ValueError("EXECUTION_SNAPSHOT_FILE_SET_INVALID")
        if ({"source/" + key: value for key, value in source_files.items()}
                != {key: value for key, value in files.items() if key.startswith("source/")}):
            raise ValueError("EXECUTION_SNAPSHOT_SOURCE_INVALID")
        for relative, metadata in files.items():
            if relative.startswith("config/") or relative == "assets/common/geometry-manifest.yaml":
                if metadata != source_files.get("src/so101_demo_py/" + relative):
                    raise ValueError("EXECUTION_SNAPSHOT_SOURCE_COPY_MISMATCH")
        if document["source_sha256"] != _sha(_canonical({"kind": "ACT_DIAGNOSTIC_EPISODE_SOURCE",
                                                         "schema_version": 1, "files": source_files})):
            raise ValueError("EXECUTION_SNAPSHOT_SOURCE_INVALID")
        derived = _model_and_targets(root, document["scene_path"])
        if any(document[key] != value for key, value in derived.items()):
            raise ValueError("EXECUTION_SNAPSHOT_RECIPE_INVALID")
        return document
    except (OSError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("EXECUTION_SNAPSHOT_INVALID") from error
