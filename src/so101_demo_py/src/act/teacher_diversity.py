"""R3-a: the Teacher diversity block of the execution policy (schema 6) and the per-episode values derived from it.

The block holds distributions and one campaign seed and is frozen with the execution policy. Each episode's actual values are a pure
function of (campaign seed, scene id): the same inputs give the same values on every host, and they are recorded in the case inputs,
the Teacher manifest and the episode identity. Every value is range-checked when the policy loads, when it is derived and when it is
read back. The module is standalone: it reads no runtime state and imports MuJoCo only inside the start-pose collision check.

Axes (design 2026-10-23-so101-domain-randomization-design-update, R3-a): the start joint pose (task_start plus a uniform offset per
arm joint), the pre-grasp and place-approach heights, one carry via-point in a box around the lift to above-place midpoint, a speed
scale and the OMPL planning attempts. Deferred and deliberately absent: approach yaw and roll, the grasp height and the gripper close
target (they move the endpoint targets, the place-height calibration band and the contact calibration).
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from pathlib import Path

CODE = "TEACHER_DIVERSITY_INVALID"
VALUES_SCHEMA = 1
RECIPE = "teacher-diversity-recipe"
#: the arm joints the start pose varies (the gripper, and the neck of a neck rig, stay at their reset value)
START_JOINTS = ("1", "2", "3", "4", "5")
BLOCK_FIELDS = frozenset({"campaign_seed", "start_pose", "pregrasp_height", "place_approach_height", "carry_via", "speed_scale", "ompl"})
VALUES_FIELDS = frozenset({"schema", "scene_id", "campaign_seed", "start_pose", "pregrasp_height_offset_m",
                           "place_approach_height_offset_m", "carry_via_offset_m", "speed_scale", "ompl"})
START_POSE_FIELDS = frozenset({"draw_index", "joints", "offsets_rad"})
OMPL_FIELDS = frozenset({"num_planning_attempts", "seed", "seed_applied"})
#: the hard caps: the ranges a campaign may declare are inside these, whatever the policy file says
START_HALF_RANGE_CAP_RAD = 0.30
HEIGHT_HALF_RANGE_CAP_M = 0.03
VIA_HALF_EXTENT_CAP_M = 0.06
SPEED_LOW_RANGE = (0.5, 1.0)
SPEED_HIGH_RANGE = (1.0, 1.5)
MAX_REDRAWS_CAP = 32
MAX_ATTEMPTS_CAP = 10
SEED_LIMIT = 2 ** 63
#: the measured start pose is matched to its draw within this many radians (the arm settles within the reset gate's 0.002)
START_MATCH_TOLERANCE_RAD = 0.005
#: the margin from the simulator joint limits that a drawn start pose keeps
START_LIMIT_MARGIN_RAD = 0.02
#: the check ranges are exact; this slack only absorbs the rounding of a value that went through JSON
_RANGE_SLACK = 1e-12


def _fail(message: str):
    raise ValueError(f"{CODE}: {message}")


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{name} is not a finite number")
    return float(value)


def _integer(value, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(f"{name} is not an integer within {low} to {high}")
    return value


def _closed(value, fields, name: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(fields):
        _fail(f"{name} is not the closed block")
    return value


def _distribution(value, name: str, expected: str) -> str:
    if value != expected:
        _fail(f"{name}.distribution is not {expected}")
    return expected


def parse_diversity(document) -> dict:
    """The canonical diversity block, or ``ValueError(TEACHER_DIVERSITY_INVALID...)`` for any missing, extra, mistyped or out-of-range field."""

    block = _closed(document, BLOCK_FIELDS, "diversity")
    seed = block["campaign_seed"]
    if type(seed) is not int or not 0 <= seed < SEED_LIMIT:
        _fail("campaign_seed is not an integer within 0 to 2^63-1")
    start = _closed(block["start_pose"], {"distribution", "half_range_rad", "max_redraws"}, "start_pose")
    half = _number(start["half_range_rad"], "start_pose.half_range_rad")
    if not 0 <= half <= START_HALF_RANGE_CAP_RAD:
        _fail(f"start_pose.half_range_rad is not within [0, {START_HALF_RANGE_CAP_RAD}] (0 switches the start pose axis off)")
    parsed = {
        "campaign_seed": seed,
        "start_pose": {"distribution": _distribution(start["distribution"], "start_pose", "uniform"), "half_range_rad": half,
                       "max_redraws": _integer(start["max_redraws"], "start_pose.max_redraws", 1, MAX_REDRAWS_CAP)},
    }
    for name in ("pregrasp_height", "place_approach_height"):
        axis = _closed(block[name], {"distribution", "half_range_m"}, name)
        height = _number(axis["half_range_m"], f"{name}.half_range_m")
        if not 0 <= height <= HEIGHT_HALF_RANGE_CAP_M:
            _fail(f"{name}.half_range_m is not within [0, {HEIGHT_HALF_RANGE_CAP_M}]")
        parsed[name] = {"distribution": _distribution(axis["distribution"], name, "uniform"), "half_range_m": height}
    via = _closed(block["carry_via"], {"distribution", "half_extent_m"}, "carry_via")
    extent = via["half_extent_m"]
    if not isinstance(extent, list) or len(extent) != 3:
        _fail("carry_via.half_extent_m is not three numbers")
    extent = [_number(item, "carry_via.half_extent_m") for item in extent]
    if any(not 0 <= item <= VIA_HALF_EXTENT_CAP_M for item in extent):
        _fail(f"carry_via.half_extent_m is not within [0, {VIA_HALF_EXTENT_CAP_M}] per axis")
    parsed["carry_via"] = {"distribution": _distribution(via["distribution"], "carry_via", "uniform_box"), "half_extent_m": extent}
    speed = _closed(block["speed_scale"], {"distribution", "low", "high"}, "speed_scale")
    low, high = _number(speed["low"], "speed_scale.low"), _number(speed["high"], "speed_scale.high")
    if not SPEED_LOW_RANGE[0] <= low <= SPEED_LOW_RANGE[1] or not SPEED_HIGH_RANGE[0] <= high <= SPEED_HIGH_RANGE[1] or low > high:
        _fail(f"speed_scale is not within low {SPEED_LOW_RANGE} and high {SPEED_HIGH_RANGE}")
    parsed["speed_scale"] = {"distribution": _distribution(speed["distribution"], "speed_scale", "uniform"), "low": low, "high": high}
    ompl = _closed(block["ompl"], {"num_planning_attempts"}, "ompl")
    parsed["ompl"] = {"num_planning_attempts": _integer(ompl["num_planning_attempts"], "ompl.num_planning_attempts", 1, MAX_ATTEMPTS_CAP)}
    return parsed


def _unit(seed: int, scene_id: str, axis: str, index: int, draw: int = 0) -> float:
    """A uniform number in [0, 1) that depends only on its arguments (the first eight bytes of a sha256)."""

    digest = hashlib.sha256(f"{RECIPE}|{seed}|{scene_id}|{axis}|{index}|{draw}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def _symmetric(half: float, unit: float) -> float:
    return half * (2.0 * unit - 1.0)


def _scene(scene_id) -> str:
    if not isinstance(scene_id, str) or not scene_id or scene_id != scene_id.strip():
        _fail("scene_id is not a non-empty string")
    return scene_id


def start_pose_candidates(diversity: dict, scene_id: str) -> tuple:
    """The bounded, ordered draws of the start pose offsets (rad per START_JOINTS): draw 0 first, then the redraws."""

    scene_id = _scene(scene_id)
    spec = diversity["start_pose"]
    seed = diversity["campaign_seed"]
    return tuple(
        tuple(_symmetric(spec["half_range_rad"], _unit(seed, scene_id, "start_pose", joint, draw)) for joint in range(len(START_JOINTS)))
        for draw in range(spec["max_redraws"] + 1))


def derive_episode_values(diversity: dict, scene_id: str, start_draw: int = 0) -> dict:
    """The per-episode values of (campaign seed, scene id). ``start_pose`` is draw ``start_draw`` (0 unless the reset kept a later one:
    the draw `select_start_pose` accepted, carried to the Teacher and the episode identity)."""

    scene_id = _scene(scene_id)
    if type(start_draw) is not int or not 0 <= start_draw <= diversity["start_pose"]["max_redraws"]:
        _fail("start_draw is not a draw of the bounded list")
    seed = diversity["campaign_seed"]
    low, high = diversity["speed_scale"]["low"], diversity["speed_scale"]["high"]
    via = diversity["carry_via"]["half_extent_m"]
    values = {
        "schema": VALUES_SCHEMA,
        "scene_id": scene_id,
        "campaign_seed": seed,
        "start_pose": {"draw_index": start_draw, "joints": list(START_JOINTS),
                       "offsets_rad": list(start_pose_candidates(diversity, scene_id)[start_draw])},
        "pregrasp_height_offset_m": _symmetric(diversity["pregrasp_height"]["half_range_m"], _unit(seed, scene_id, "pregrasp_height", 0)),
        "place_approach_height_offset_m": _symmetric(
            diversity["place_approach_height"]["half_range_m"], _unit(seed, scene_id, "place_approach_height", 0)),
        # x and y are symmetric about the lift to above-place midpoint; z is one-sided, 0 to the extent: the via-point is never lower
        # than the line (review 2026-10-24: the carried cup must not dip toward the table)
        "carry_via_offset_m": [_symmetric(via[0], _unit(seed, scene_id, "carry_via", 0)), _symmetric(via[1], _unit(seed, scene_id, "carry_via", 1)),
                               via[2] * _unit(seed, scene_id, "carry_via", 2)],
        "speed_scale": low + (high - low) * _unit(seed, scene_id, "speed_scale", 0),
        # MoveIt's GetMotionPlan request has no seed field (OMPL seeds its generator once per process), so the seed is derived and
        # recorded as the requested one, and `seed_applied` says it is not delivered: the planner's output is recorded instead.
        "ompl": {"num_planning_attempts": diversity["ompl"]["num_planning_attempts"],
                 "seed": int.from_bytes(hashlib.sha256(f"{RECIPE}|{seed}|{scene_id}|ompl".encode()).digest()[:4], "big") & 0x7FFFFFFF,
                 "seed_applied": False},
    }
    return values


def values_for_policy(policy, scene_id: str, start_draw: int | None = None):
    """The checked per-episode values of a loaded Teacher execution policy, or None for a policy without a diversity block
    (schema 3, 4 and 5: nothing varies, and nothing is recorded). ``start_draw`` is the start pose draw the reset applied (default 0)."""

    diversity = None if not isinstance(policy, dict) else policy.get("diversity")
    if diversity is None:
        return None
    values = derive_episode_values(diversity, scene_id, 0 if start_draw is None else start_draw)
    # the derived values are checked against the draw they carry, not draw 0
    return validate_episode_values(diversity, values, expect_derived=True)


def start_pose_matches(diversity: dict, scene_id: str, measured_joints, draw: int,
                       tolerance_rad: float = START_MATCH_TOLERANCE_RAD) -> bool:
    """True when the measured start joints (arm joints first) are the pose of exactly this draw. Another draw that happens to match is not it."""

    try:
        measured = [float(item) for item in measured_joints]
        offsets = start_pose_candidates(diversity, scene_id)[draw]
    except (TypeError, ValueError, IndexError):
        return False
    if len(measured) not in (6, 7) or any(not math.isfinite(item) for item in measured):
        return False
    return all(abs(measured[index] - offsets[index]) <= tolerance_rad for index in range(len(START_JOINTS)))


def frozen_scene_identity(frozen, snapshot):
    """The scene and compiled-model hashes of a frozen input set: the sha256 of its `scene_model` role file and the `model_sha256` of its
    verified execution snapshot (the compile of that scene). None when either is missing."""

    try:
        scene = frozen["roles"]["scene_model"]["sha256"]
        model = snapshot["model_sha256"]
    except (KeyError, TypeError):
        return None
    if not all(isinstance(item, str) and len(item) == 64 for item in (scene, model)):
        return None
    return {"scene_sha256": scene, "model_sha256": model}


SELECTION_KIND = "TEACHER_DIVERSITY_START_POSE_SELECTION"


def read_start_pose_selection(root, attempt_id: str):
    """The start pose selection the reset wrote for an attempt (`start-pose-<attempt>.json` in the task root), or None when there is none.

    A file that is not the closed selection document is refused (``TEACHER_DIVERSITY_START_POSE_RECORD_INVALID``)."""

    import json

    path = Path(root) / f"start-pose-{attempt_id}.json"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("TEACHER_DIVERSITY_START_POSE_RECORD_INVALID") from error
    try:
        document = json.loads(raw)
    except ValueError as error:
        raise ValueError("TEACHER_DIVERSITY_START_POSE_RECORD_INVALID") from error
    if (not isinstance(document, dict) or document.get("kind") != SELECTION_KIND or document.get("attempt_id") != attempt_id
            or type(document.get("draw_index")) is not int or document["draw_index"] < 0):
        raise ValueError("TEACHER_DIVERSITY_START_POSE_RECORD_INVALID")
    return document


def _within(value: float, low: float, high: float) -> bool:
    return low - _RANGE_SLACK <= value <= high + _RANGE_SLACK


def validate_episode_values(diversity: dict, values, *, expect_derived: bool = False) -> dict:
    """Check derived values against the declared ranges and the closed shape; with ``expect_derived`` also against the derivation.

    Returns ``values``. Raises ``ValueError(TEACHER_DIVERSITY_INVALID...)``. The start pose may be any draw of the bounded list."""

    document = _closed(values, VALUES_FIELDS, "episode values")
    if document["schema"] != VALUES_SCHEMA or type(document["schema"]) is not int:
        _fail("episode values schema is unknown")
    scene_id = _scene(document["scene_id"])
    if document["campaign_seed"] != diversity["campaign_seed"] or type(document["campaign_seed"]) is not int:
        _fail("episode values name another campaign seed")
    start = document["start_pose"]
    if not isinstance(start, dict) or not START_POSE_FIELDS <= set(start) or not set(start) <= START_POSE_FIELDS | {"rejected"}:
        _fail("start_pose is not the closed block")
    spec = diversity["start_pose"]
    draw = _integer(start["draw_index"], "start_pose.draw_index", 0, spec["max_redraws"])
    if start["joints"] != list(START_JOINTS):
        _fail("start_pose.joints is not the arm joints")
    offsets = start["offsets_rad"]
    if not isinstance(offsets, list) or len(offsets) != len(START_JOINTS):
        _fail("start_pose.offsets_rad is not one offset per arm joint")
    for item in offsets:
        if not _within(abs(_number(item, "start_pose.offsets_rad")), 0.0, spec["half_range_rad"]):
            _fail("a start pose offset is outside its range")
    for name in ("pregrasp_height", "place_approach_height"):
        key = f"{name}_offset_m"
        if not _within(abs(_number(document[key], key)), 0.0, diversity[name]["half_range_m"]):
            _fail(f"{key} is outside its range")
    via = document["carry_via_offset_m"]
    if not isinstance(via, list) or len(via) != 3:
        _fail("carry_via_offset_m is not three numbers")
    for axis, item in enumerate(via):
        value = _number(item, "carry_via_offset_m")
        extent = diversity["carry_via"]["half_extent_m"][axis]
        if not (_within(value, 0.0, extent) if axis == 2 else _within(abs(value), 0.0, extent)):
            _fail("carry_via_offset_m is outside its box (x and y symmetric, z from 0 up)")
    if not _within(_number(document["speed_scale"], "speed_scale"), diversity["speed_scale"]["low"], diversity["speed_scale"]["high"]):
        _fail("speed_scale is outside its range")
    ompl = _closed(document["ompl"], OMPL_FIELDS, "ompl")
    if ompl["num_planning_attempts"] != diversity["ompl"]["num_planning_attempts"] or type(ompl["num_planning_attempts"]) is not int:
        _fail("ompl.num_planning_attempts is not the declared value")
    _integer(ompl["seed"], "ompl.seed", 0, 0x7FFFFFFF)
    if ompl["seed_applied"] is not False:
        _fail("ompl.seed_applied must be false: MoveIt takes no planner seed")
    if expect_derived:
        derived = derive_episode_values(diversity, scene_id)
        candidate = start_pose_candidates(diversity, scene_id)[draw]
        if offsets != list(candidate) or {key: value for key, value in document.items() if key != "start_pose"} != {
                key: value for key, value in derived.items() if key != "start_pose"}:
            _fail("episode values differ from their derivation")
    return document


def select_start_pose(diversity: dict, scene_id: str, check) -> dict:
    """The first draw of the start pose that ``check(offsets) -> (accepted, reason)`` accepts.

    The number of draws is bounded by ``max_redraws + 1``; a campaign that rejects every one fails closed
    (``TEACHER_DIVERSITY_START_POSE_REJECTED``), never falls back to an unvaried pose. The result carries the rejected draws."""

    rejected = []
    for draw, offsets in enumerate(start_pose_candidates(diversity, scene_id)):
        accepted, reason = check(offsets)
        if accepted:
            return {"draw_index": draw, "joints": list(START_JOINTS), "offsets_rad": list(offsets), "rejected": rejected}
        rejected.append({"draw_index": draw, "reason": str(reason)})
    raise ValueError("TEACHER_DIVERSITY_START_POSE_REJECTED: every draw was rejected: "
                     + "; ".join(f"{item['draw_index']}={item['reason']}" for item in rejected)[:400])


def matching_start_draw(diversity: dict, scene_id: str, measured_joints, tolerance_rad: float = START_MATCH_TOLERANCE_RAD):
    """The first draw index whose offsets the measured start joints (arm joints first) match, else None."""

    try:
        measured = [float(item) for item in measured_joints]
    except (TypeError, ValueError):
        return None
    if len(measured) not in (6, 7) or any(not math.isfinite(item) for item in measured):
        return None
    for draw, offsets in enumerate(start_pose_candidates(diversity, scene_id)):
        if all(abs(measured[index] - offsets[index]) <= tolerance_rad for index in range(len(START_JOINTS))):
            return draw
    return None


def reset_joint_positions(offsets, joint_names) -> tuple:
    """The full reset joint vector (task_start is all zero): the offsets on the arm joints, zero on the gripper and the neck."""

    by_name = dict(zip(START_JOINTS, offsets, strict=True))
    return tuple(float(by_name.get(name, 0.0)) for name in joint_names)


def joints_within_limits(positions, *, margin_rad: float = START_LIMIT_MARGIN_RAD) -> bool:
    """True when the six arm joint positions keep ``margin_rad`` from the ACT simulator limits."""

    from .joints import ARM_JOINTS, joint_limits_for

    limits = joint_limits_for("act")
    try:
        values = [float(item) for item in positions][:len(ARM_JOINTS)]
    except (TypeError, ValueError):
        return False
    if len(values) != len(ARM_JOINTS):
        return False
    return all(math.isfinite(value) and limits[name][0] + margin_rad <= value <= limits[name][1] - margin_rad
               for name, value in zip(ARM_JOINTS, values))


def carry_via_position(lift_position, above_place_position, offset) -> tuple:
    """The carry via-point: the midpoint of the lift and above-place positions plus the offset."""

    return tuple(float((a + b) / 2.0 + o) for a, b, o in zip(lift_position, above_place_position, offset, strict=True))


def scaled_scaling(value: float, scale: float) -> float:
    """A MoveIt scaling factor times the speed scale, capped at 1."""

    if not 0 < _number(value, "scaling") <= 1 or not _number(scale, "speed_scale") > 0:
        _fail("scaling or speed scale is outside (0, 1] or positive")
    return min(1.0, value * scale)


def episode_template(template, values: dict):
    """The template of one episode: the pre-grasp and place-approach clearances shifted by the derived offsets, nothing else."""

    return dataclasses.replace(
        template,
        pregrasp_world_z_clearance_m=template.pregrasp_world_z_clearance_m + values["pregrasp_height_offset_m"],
        place_approach_world_z_clearance_m=template.place_approach_world_z_clearance_m + values["place_approach_height_offset_m"])


class StartPoseCollisionCheck:
    """The MuJoCo collision check of a reset pose: set the joints on the reset keyframe, run the forward kinematics, list the contacts.

    A pose is rejected when a joint leaves the model's range, or when a contact exists that the unvaried reset keyframe does not have.
    Nothing is stepped, so the check is deterministic and independent of the running simulator."""

    def __init__(self, model, *, cup_body: str, joint_names, keyframe: str = "task_start") -> None:
        import mujoco

        self._mujoco = mujoco
        self._model = model
        self._data = mujoco.MjData(model)
        self._joint_names = tuple(joint_names)
        self._key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, keyframe)
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, cup_body)
        if self._key < 0 or body < 0 or model.body_jntnum[body] != 1:
            raise ValueError("TEACHER_DIVERSITY_START_POSE_MODEL_INVALID")
        self._cup_qpos = int(model.jnt_qposadr[model.body_jntadr[body]])
        self._joints = []
        for name in self._joint_names:
            joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0:
                raise ValueError("TEACHER_DIVERSITY_START_POSE_MODEL_INVALID")
            self._joints.append(joint)
        # the baseline is the reset keyframe, not qpos0: a fresh MjData holds qpos0, whose contacts are not the reset state's
        self._mujoco.mj_resetDataKeyframe(model, self._data, self._key)
        self._baseline = self._contacts()
        self._scene_path = None
        self._identity = None

    @classmethod
    def from_xml_string(cls, xml: str, **options) -> "StartPoseCollisionCheck":
        import mujoco

        return cls(mujoco.MjModel.from_xml_string(xml), **options)

    @classmethod
    def from_path(cls, path, **options) -> "StartPoseCollisionCheck":
        import mujoco

        checker = cls(mujoco.MjModel.from_xml_path(str(Path(path))), **options)
        checker._scene_path = Path(path)
        return checker

    def identity(self) -> dict:
        """The model this check ran on: the scene file's sha256 (None for a model built from a string), the sha256 of the compiled model
        (the recipe of the execution snapshot's `model_sha256`), both physics fingerprints and the MuJoCo version."""

        if self._identity is None:
            import hashlib

            import numpy as np

            from .physics_fingerprint import physics_fingerprint, stripped_physics_fingerprint_of_file

            buffer = np.empty(self._mujoco.mj_sizeModel(self._model), dtype=np.uint8)
            self._mujoco.mj_saveModel(self._model, None, buffer)
            path = self._scene_path
            self._identity = {
                "scene_sha256": None if path is None else hashlib.sha256(path.read_bytes()).hexdigest(),
                "model_sha256": hashlib.sha256(buffer.tobytes()).hexdigest(),
                "physics_fingerprint": physics_fingerprint(self._model),
                "physics_fingerprint_stripped": None if path is None else stripped_physics_fingerprint_of_file(path),
                "mujoco_version": self._mujoco.__version__}
        return dict(self._identity)

    def _geom(self, identifier: int) -> str:
        name = self._mujoco.mj_id2name(self._model, self._mujoco.mjtObj.mjOBJ_GEOM, identifier)
        return name or f"geom{identifier}"

    def _contacts(self) -> set:
        self._mujoco.mj_forward(self._model, self._data)
        return {frozenset((self._geom(item.geom1), self._geom(item.geom2))) for item in self._data.contact[:self._data.ncon]}

    def check(self, joints, cup_position=None):
        """(accepted, reason) of the joint vector (in ``joint_names`` order); the reason is empty when accepted."""

        model, data = self._model, self._data
        values = [float(item) for item in joints]
        if len(values) != len(self._joints) or any(not math.isfinite(item) for item in values):
            return False, "JOINT_LIMIT: the joint vector is incomplete or not finite"
        self._mujoco.mj_resetDataKeyframe(model, data, self._key)
        for name, joint, value in zip(self._joint_names, self._joints, values, strict=True):
            if model.jnt_limited[joint]:
                low, high = (float(item) for item in model.jnt_range[joint])
                if not low <= value <= high:
                    return False, f"JOINT_LIMIT: joint {name} {value:.4f} is outside [{low:.4f}, {high:.4f}]"
            data.qpos[model.jnt_qposadr[joint]] = value
        if cup_position is not None:
            data.qpos[self._cup_qpos:self._cup_qpos + 3] = [float(item) for item in cup_position]
        # the baseline is the unvaried reset keyframe: a contact it already has (none today) is not the pose's doing
        extra = self._contacts() - self._baseline
        if extra:
            pair = sorted("|".join(sorted(item)) for item in extra)
            return False, "COLLISION: " + ", ".join(pair)[:300]
        return True, ""
