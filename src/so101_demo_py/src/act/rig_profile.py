"""The ACT camera rig profile: camera names, topics, frame-file keys, head/neck presence and the state layout as data.

A profile is a closed YAML document (`config/act/rig-v1.yaml`, `config/act/rig-v2.yaml`). Every component that used to
hard-code a `head`/`wrist` pair, a neck or an 8-wide state reads it instead.

Where the active profile comes from:

* collection and processing: the frozen inputs manifest (`rig_profile` binding, `rig_from_frozen`) and the campaign config;
* training, export and rollout: the bundle's `normalization.observation` (`cameras`, `state_dim`; `rig_from_observation`);
* a caller that has neither (a unit test, a tool pointed at old data) passes `HEAD_WRIST_RIG` explicitly.

Two rigs are known. `rig-v1.yaml` and `rig-v2.yaml` are the confirmed design's names for them (rig v1: head and wrist cameras with
the neck, the sealed EXP-620/622 data; rig v2: side and wrist cameras, no head, no neck). In code and in manifests they are
`HEAD_WRIST_RIG` (`rig: head-wrist`) and `SIDE_WRIST_RIG` (`rig: side-wrist`); the constants are the content of the YAML files
(a test pins that).

`HEAD_WRIST_RIG` (= `DEFAULT_RIG`) is the default ONLY where an already sealed artifact carries no profile (a frozen manifest
without the `rig_profile` key and so its audits and episodes, a campaign config without `rig_profile_sha256`, a bundle without an
observation declaration). Every newly written frozen set, controlled identity of a campaign that names a rig, and bundle records
its profile.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

KIND = "act_rig_profile"
SCHEMA_VERSION = 1
_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_TOP_KEYS = frozenset({"kind", "schema_version", "rig", "cameras", "has_head", "has_neck", "state"})
_CAMERA_KEYS = frozenset({"name", "image_topic", "info_topic", "frame_key"})
_STATE_KEYS = frozenset({"arm_joints", "neck_features", "state_dim"})
NECK_FEATURES = ("neck_sin", "neck_cos")
ARM_JOINTS = ("1", "2", "3", "4", "5", "6")


@dataclass(frozen=True)
class RigCamera:
    name: str
    image_topic: str
    info_topic: str
    frame_key: str


@dataclass(frozen=True)
class RigProfile:
    rig: str
    cameras: tuple[RigCamera, ...]
    has_head: bool
    has_neck: bool
    arm_joints: tuple[str, ...]
    neck_features: tuple[str, ...]
    state_dim: int
    document: dict

    @property
    def camera_names(self) -> tuple[str, ...]:
        return tuple(camera.name for camera in self.cameras)

    @property
    def frame_keys(self) -> tuple[str, ...]:
        return tuple(camera.frame_key for camera in self.cameras)

    @property
    def image_topics(self) -> tuple[str, ...]:
        return tuple(camera.image_topic for camera in self.cameras)

    @property
    def info_topics(self) -> tuple[str, ...]:
        return tuple(camera.info_topic for camera in self.cameras)

    @property
    def camera_topics(self) -> tuple[str, ...]:
        """Per camera: the image topic, then its camera_info topic, in camera order."""
        return tuple(topic for camera in self.cameras for topic in (camera.image_topic, camera.info_topic))

    @property
    def color_topics(self) -> dict:
        """image topic -> its camera_info topic."""
        return {camera.image_topic: camera.info_topic for camera in self.cameras}

    @property
    def decode_table(self) -> tuple[tuple[str, str], ...]:
        """(stored frame key, runtime camera name) per camera: the D8 decode table of this rig."""
        return tuple((camera.frame_key, camera.name) for camera in self.cameras)

    @property
    def arm_dim(self) -> int:
        return len(self.arm_joints)

    @property
    def profile_sha256(self) -> str:
        """sha256 of the canonical JSON of the validated document (the rig's identity wherever it is bound)."""
        return profile_sha256(self.document)

    def camera(self, name: str) -> RigCamera:
        for camera in self.cameras:
            if camera.name == name:
                return camera
        raise KeyError(name)

    def frame_key(self, name: str) -> str:
        return self.camera(name).frame_key

    def observation_spec(self, action_dim: int = 6) -> dict:
        """The `observation` block a bundle's normalization / a training config declares."""
        return {"cameras": list(self.camera_names), "state_dim": self.state_dim, "action_dim": action_dim}


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def profile_sha256(document: dict) -> str:
    return hashlib.sha256(_canonical(document)).hexdigest()


def validate_rig_profile(document) -> RigProfile:
    """The profile of a parsed document; every shape error is `ValueError('RIG_PROFILE_INVALID: ...')`."""

    def refuse(reason):
        raise ValueError("RIG_PROFILE_INVALID: " + reason)

    if not isinstance(document, dict) or set(document) != _TOP_KEYS:
        refuse("keys")
    if document["kind"] != KIND or document["schema_version"] != SCHEMA_VERSION:
        refuse("kind or schema_version")
    rig = document["rig"]
    if not isinstance(rig, str) or _NAME.fullmatch(rig.replace("-", "_")) is None:
        refuse("rig")
    for key in ("has_head", "has_neck"):
        if type(document[key]) is not bool:
            refuse(key)
    rows = document["cameras"]
    if not isinstance(rows, list) or not rows:
        refuse("cameras")
    cameras = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != _CAMERA_KEYS:
            refuse("camera keys")
        name = row["name"]
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            refuse("camera name")
        # the plugin config convention: camera `<name>` is the plugin `<name>_camera`
        if (row["image_topic"] != f"/{name}_camera/color" or row["info_topic"] != f"/{name}_camera/camera_info"
                or row["frame_key"] != f"{name}_png"):
            refuse("camera naming convention: " + name)
        cameras.append(RigCamera(name, row["image_topic"], row["info_topic"], row["frame_key"]))
    names = [camera.name for camera in cameras]
    if len(set(names)) != len(names):
        refuse("duplicate camera")
    if ("head" in names) != document["has_head"]:
        refuse("has_head disagrees with the cameras")
    if document["has_neck"] and not document["has_head"]:
        refuse("a neck without a head")
    state = document["state"]
    if not isinstance(state, dict) or set(state) != _STATE_KEYS:
        refuse("state keys")
    arm, neck, dim = state["arm_joints"], state["neck_features"], state["state_dim"]
    if not isinstance(arm, list) or tuple(arm) != ARM_JOINTS:
        refuse("arm_joints")
    if not isinstance(neck, list) or tuple(neck) != (NECK_FEATURES if document["has_neck"] else ()):
        refuse("neck_features disagree with has_neck")
    if type(dim) is not int or dim != len(arm) + len(neck):
        refuse("state_dim")
    return RigProfile(rig, tuple(cameras), document["has_head"], document["has_neck"], tuple(arm), tuple(neck), dim,
                      json.loads(_canonical(document)))


def load_rig_profile_bytes(payload: bytes) -> RigProfile:
    try:
        document = yaml.safe_load(payload)
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ValueError("RIG_PROFILE_INVALID: unparsable") from error
    return validate_rig_profile(document)


def dump_rig_profile(profile: RigProfile) -> bytes:
    """The YAML bytes of a profile (the profile digest depends on the document, not on these bytes)."""
    return yaml.safe_dump(profile.document, sort_keys=False).encode("utf-8")


def load_rig_profile(path) -> RigProfile:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("RIG_PROFILE_MISSING")
    return load_rig_profile_bytes(target.read_bytes())


HEAD_WRIST_RIG = validate_rig_profile({
    "kind": KIND, "schema_version": SCHEMA_VERSION, "rig": "head-wrist",
    "cameras": [{"name": "head", "image_topic": "/head_camera/color", "info_topic": "/head_camera/camera_info",
                 "frame_key": "head_png"},
                {"name": "wrist", "image_topic": "/wrist_camera/color", "info_topic": "/wrist_camera/camera_info",
                 "frame_key": "wrist_png"}],
    "has_head": True, "has_neck": True,
    "state": {"arm_joints": list(ARM_JOINTS), "neck_features": list(NECK_FEATURES), "state_dim": 8}})

SIDE_WRIST_RIG = validate_rig_profile({
    "kind": KIND, "schema_version": SCHEMA_VERSION, "rig": "side-wrist",
    "cameras": [{"name": "side", "image_topic": "/side_camera/color", "info_topic": "/side_camera/camera_info",
                 "frame_key": "side_png"},
                {"name": "wrist", "image_topic": "/wrist_camera/color", "info_topic": "/wrist_camera/camera_info",
                 "frame_key": "wrist_png"}],
    "has_head": False, "has_neck": False,
    "state": {"arm_joints": list(ARM_JOINTS), "neck_features": [], "state_dim": 6}})

KNOWN_RIGS = {profile.rig: profile for profile in (HEAD_WRIST_RIG, SIDE_WRIST_RIG)}
#: The profile of every artifact sealed before profiles existed.
DEFAULT_RIG = HEAD_WRIST_RIG


def known_rig(name: str) -> RigProfile:
    try:
        return KNOWN_RIGS[name]
    except KeyError:
        raise ValueError("RIG_PROFILE_UNKNOWN: " + str(name)) from None


def rig_from_frozen(frozen: dict) -> RigProfile:
    """The rig a verified frozen inputs manifest binds; a manifest sealed before profiles existed is rig v1 (the default)."""
    binding = frozen.get("rig_profile")
    if binding is None:
        return DEFAULT_RIG
    profile = validate_rig_profile(binding["values"])
    # a bound profile equal to a known one is that one (one object per known rig)
    return next((known for known in KNOWN_RIGS.values() if known.document == profile.document), profile)


def rig_from_profile_sha256(digest) -> RigProfile:
    """The known rig a campaign config's `rig_profile_sha256` names; None (a config written before profiles) is the default rig."""
    if digest is None:
        return DEFAULT_RIG
    for profile in KNOWN_RIGS.values():
        if profile.profile_sha256 == digest:
            return profile
    raise ValueError("RIG_PROFILE_UNKNOWN: " + str(digest))


def rig_from_observation(cameras, state_dim) -> RigProfile:
    """The known rig whose cameras (in order) and state width are those a bundle's `normalization.observation` declares."""
    names = tuple(cameras)
    for profile in KNOWN_RIGS.values():
        if profile.camera_names == names and profile.state_dim == state_dim:
            return profile
    raise ValueError(f"RIG_PROFILE_UNKNOWN: cameras={list(names)} state_dim={state_dim}")


def rig_from_frame_keys(keys) -> RigProfile:
    """The known rig whose stored frame keys (`<camera>_png`) are exactly the `_png` keys among `keys` (a stored observation)."""
    found = {key for key in keys if isinstance(key, str) and key.endswith("_png")}
    for profile in KNOWN_RIGS.values():
        if set(profile.frame_keys) == found:
            return profile
    raise ValueError(f"RIG_PROFILE_UNKNOWN: frame keys {sorted(found)}")


def source_keys_for(rig: RigProfile) -> tuple:
    """The sources of one physical sample of a rig, in order: world, scene, contact, its cameras, the arm and (only with a neck) the neck."""
    return ("world", "scene", "contact", *rig.camera_names, "arm", *(("neck",) if rig.has_neck else ()))


#: the source key tuple of every known rig: the closed set a stored receipt or sample must match one of
KNOWN_SOURCE_KEYS = tuple(source_keys_for(profile) for profile in KNOWN_RIGS.values())


def stack_state(profile: RigProfile, arm, neck_yaw=None) -> tuple:
    """The state vector of a rig from the arm joints (and the neck yaw, in radians, when the rig has a neck)."""
    import math

    arm = tuple(float(value) for value in arm)
    if len(arm) != profile.arm_dim:
        raise ValueError("STATE_ARM_WIDTH_INVALID")
    if not profile.has_neck:
        return arm
    if neck_yaw is None:
        raise ValueError("STATE_NECK_REQUIRED")
    return arm + (math.sin(neck_yaw), math.cos(neck_yaw))
