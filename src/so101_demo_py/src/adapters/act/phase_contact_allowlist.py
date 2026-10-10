"""Exact phase contact allowlists from an activated MuJoCo policy and model."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import mujoco

from so101_demo.act.contact_calibration import proposal_validation_mode, verify_disabled_proposal
from so101_demo.act.contact_policy import verify_activation
from so101_demo.act.contracts import sha256
from .physics import model_sha256


def _read_json_file(path: Path) -> dict:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("artifact path must be absolute")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("artifact must be a regular file")
        raw = stream.read((1 << 20) + 1)
    if len(raw) > (1 << 20):
        raise ValueError("artifact is too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("artifact is not an object")
    return value


def stationary_cup_support_pairs(model: mujoco.MjModel) -> frozenset[tuple[str, str]]:
    """Identify the existing cup/table support pairs, without motion authority.

    Offline approaches leave the cup at its source pose. They still check its
    whole volume and must explicitly list its stationary table support.
    """
    cup = set()
    table = set()
    for geom in range(model.ngeom):
        body = int(model.geom_bodyid[geom])
        body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body)
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom)
        if not model.geom_contype[geom] or not model.geom_conaffinity[geom]:
            continue
        if body_name == "plastic_cup" and name and name.endswith("_collision"):
            cup.add(name)
        if body_name == "table" and name == "table_collision" and model.body_dofnum[body] == 0:
            table.add(name)
    if not cup or not table:
        raise ValueError("PICK_PLACE_VALIDATION_CONTACT_SUPPORT_GEOMETRY_INVALID")
    return frozenset(tuple(sorted((a, b))) for a in cup for b in table)


class PhaseContactAllowlist:
    """Immutable phase allowlists; all unlisted contacts remain hazards.

    This only identifies permitted geometry pairs. Contact force, compression,
    holding state and support still require independent physical supervision.
    """

    PHASES = (
        "SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT",
        "ALIGN", "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK",
    )
    _FINGERTIP_PHASES = frozenset(
        {"CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE"}
    )
    _SUPPORT_PHASES = frozenset(
        {"SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "RELEASE",
         "RADIAL_RETREAT", "FINAL_CHECK"}
    )

    def __init__(
        self, *, model: mujoco.MjModel, scene_path: Path, proposal_path: Path,
        receipt_path: Path, expected_fingerprint: str, allow_spot_check_candidate: bool = False,
    ) -> None:
        try:
            sha256(expected_fingerprint)
            proposal = _read_json_file(Path(proposal_path))
            receipt = _read_json_file(Path(receipt_path))
            verify_disabled_proposal(proposal, validation_mode=proposal_validation_mode(proposal))
            if proposal["policy_fingerprint"] != expected_fingerprint:
                raise ValueError("admitted fingerprint mismatch")
            if not isinstance(model, mujoco.MjModel):
                raise ValueError("compiled model required")
            scene = Path(scene_path)
            if not scene.is_absolute() or ".." in scene.parts or not scene.is_file():
                raise ValueError("scene path invalid")
            payload = proposal["payload"]
            verify_activation(
                payload, receipt, expected_model_sha256=model_sha256(model),
                expected_scene_sha256=hashlib.sha256(scene.read_bytes()).hexdigest(),
                expected_mujoco_version=mujoco.mj_versionString(),
                allow_spot_check_candidate=allow_spot_check_candidate,
            )
            if payload["allowed_other_contact_bodies"] != ["table"]:
                raise ValueError("unsupported other contact bodies")
            names: dict[str, tuple[str, bool]] = {}
            for geom in range(model.ngeom):
                name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom)
                body = mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_BODY, int(model.geom_bodyid[geom])
                )
                if not name or name in names or not body:
                    raise ValueError("model geometry invalid")
                names[name] = (body, bool(model.geom_contype[geom] and model.geom_conaffinity[geom]))
            cup = {name for name, (body, collidable) in names.items()
                   if body == "plastic_cup" and collidable and name.endswith("_collision")}
            table = {name for name, (body, collidable) in names.items()
                     if body == "table" and collidable and name == "table_collision"}
            left = {name for name, (body, collidable) in names.items()
                    if body == "gripper" and collidable
                    and (name.startswith("fixed_finger_contact_convex_")
                         or name.startswith("fixed_fingertip_pad_collision_"))}
            right = {name for name, (body, collidable) in names.items()
                     if body == "jaw" and collidable
                     and (name.startswith("moving_jaw_contact_convex_")
                          or name.startswith("moving_fingertip_pad_collision_"))}
            if not all((cup, table, left, right)):
                raise ValueError("required ACT collision geometry absent")
            support = stationary_cup_support_pairs(model)
            fingertips = frozenset(tuple(sorted((a, b))) for a in left | right for b in cup)
            self._pairs = {
                phase: (support if phase in self._SUPPORT_PHASES else frozenset())
                | (fingertips if phase in self._FINGERTIP_PHASES else frozenset())
                for phase in self.PHASES
            }
            self.fingerprint = expected_fingerprint
            self.model_sha256 = payload["model_sha256"]
            self.scene_sha256 = payload["scene_sha256"]
            self.known_geoms = frozenset(names)
            self._thresholds = tuple(sorted(payload['thresholds'].items()))
            self._evaluation = tuple(sorted(payload['evaluation'].items()))
        except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("PICK_PLACE_VALIDATION_CONTACT_POLICY_INVALID") from error

    @property
    def process_pairs(self) -> frozenset[tuple[str, str]]:
        """Cup process-expectation pairs: every pair that any phase allows.

        The phase tables hold only cup/table support pairs and fingertip/cup pairs. Which of them
        a phase expects (support while the cup rests, finger contact while grasping) is a process
        expectation. Any pair outside this union (robot against table, robot against robot, a
        non-finger part against the cup) is a collision and is never in it.
        """
        return frozenset().union(*self._pairs.values())

    def for_phase(self, phase: str) -> frozenset[tuple[str, str]]:
        try:
            return self._pairs[phase]
        except (KeyError, TypeError) as error:
            raise ValueError("PICK_PLACE_VALIDATION_CONTACT_PHASE_INVALID") from error

    @property
    def thresholds(self):
        return dict(self._thresholds)

    @property
    def evaluation(self):
        return dict(self._evaluation)


def load_installed_phase_contact_allowlist(
    *, proposal_path: Path, receipt_path: Path, expected_fingerprint: str,
) -> tuple[mujoco.MjModel, PhaseContactAllowlist]:
    """Compile the installed ACT scene and bind its exact activated geom pairs."""
    from ament_index_python.packages import get_package_share_directory

    try:
        scene = Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"
        if not scene.is_absolute() or not scene.is_file():
            raise ValueError("installed ACT scene unavailable")
        model = mujoco.MjModel.from_xml_path(str(scene))
        pairs = PhaseContactAllowlist(
            model=model, scene_path=scene, proposal_path=Path(proposal_path),
            receipt_path=Path(receipt_path), expected_fingerprint=expected_fingerprint,
        )
        return model, pairs
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError("PICK_PLACE_VALIDATION_CONTACT_POLICY_INVALID") from error


load_installed_act_contact_pairs = load_installed_phase_contact_allowlist
