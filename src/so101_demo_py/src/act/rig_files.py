"""The model, launch and config files of each ACT camera rig (package-relative paths).

A rig profile (`rig_profile.py`) says which cameras and state a rig has; this table says which files realise it in the simulator:
the scene (the one a MuJoCo process loads), the robot MJCF the scene includes, the URDF the ros2_control hardware and MoveIt read,
the camera plugin configuration and the controller configuration. The head+wrist rig's files are the long-standing
`assets/mujoco/act/{scene.xml,so101.xml,so101.urdf}` and `config/mujoco/act/{mujoco_plugins.yaml,ros2_controllers.yaml}`; the side+wrist
rig has its own variants, with no head body, neck joint, neck actuator, head camera or neck controller anywhere in them. The
side+wrist indoor rig (rig v3, `side-wrist-indoor`) uses the side+wrist robot MJCF, URDF, plugins and controllers unchanged and has
a scene of its own (`scene_side_wrist_indoor.xml`: the same robot, table, cup and cameras in a visual-only room).

Launch composition, the execution snapshot, the frozen inputs and the calibration identity all resolve their files here, so a rig
never reaches into another rig's files. Paths are relative to the package root (`src/so101_demo_py`) and to the installed share
directory alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rig_profile import DEFAULT_RIG, KNOWN_RIGS, RigProfile


@dataclass(frozen=True)
class RigModelFiles:
    rig: str
    scene: str
    robot_mjcf: str
    urdf: str
    plugins: str
    controllers: str
    #: the rig profile document (`rig_profile.py`) of the rig
    profile: str
    #: further scene files that belong to the rig but are not loaded by it: candidate layouts and the like (kept so that the profile
    #: identity of every other rig leaves them out, as it does the rig's own scene)
    variants: tuple = ()

    @property
    def exclusive(self) -> frozenset:
        """The files this rig uses (a file that two rigs share is in both sets and is foreign to neither)."""
        return frozenset((self.scene, self.robot_mjcf, self.urdf, self.plugins, self.controllers, *self.variants))


_HEAD_WRIST = RigModelFiles(
    "head-wrist", "assets/mujoco/act/scene.xml", "assets/mujoco/act/so101.xml", "assets/mujoco/act/so101.urdf",
    "config/mujoco/act/mujoco_plugins.yaml", "config/mujoco/act/ros2_controllers.yaml", "config/act/rig-v1.yaml")
_SIDE_WRIST = RigModelFiles(
    "side-wrist", "assets/mujoco/act/scene_side_wrist.xml", "assets/mujoco/act/so101_side_wrist.xml",
    "assets/mujoco/act/so101_side_wrist.urdf", "config/mujoco/act/mujoco_plugins_side_wrist.yaml",
    "config/mujoco/act/ros2_controllers_side_wrist.yaml", "config/act/rig-v2.yaml")

_SIDE_WRIST_INDOOR = RigModelFiles(
    "side-wrist-indoor", "assets/mujoco/act/scene_side_wrist_indoor.xml", _SIDE_WRIST.robot_mjcf, _SIDE_WRIST.urdf,
    _SIDE_WRIST.plugins, _SIDE_WRIST.controllers, "config/act/rig-v3.yaml",
    ("assets/mujoco/act/indoor/scene_side_wrist_indoor_lab.xml", "assets/mujoco/act/indoor/scene_side_wrist_indoor_home.xml"))

RIG_MODEL_FILES = {files.rig: files for files in (_HEAD_WRIST, _SIDE_WRIST, _SIDE_WRIST_INDOOR)}
#: the scene a sealed artifact without a rig names
DEFAULT_SCENE = _HEAD_WRIST.scene
KNOWN_SCENES = frozenset(files.scene for files in RIG_MODEL_FILES.values())
assert set(RIG_MODEL_FILES) == set(KNOWN_RIGS)


def rig_name(rig) -> str:
    """The rig name of a profile, a name, or None (the default rig)."""
    if rig is None:
        return DEFAULT_RIG.rig
    return rig.rig if isinstance(rig, RigProfile) else str(rig)


def rig_model_files(rig=None) -> RigModelFiles:
    """The files of a rig (a profile, a name, or None for the default rig)."""
    try:
        return RIG_MODEL_FILES[rig_name(rig)]
    except KeyError:
        raise ValueError("RIG_PROFILE_UNKNOWN: " + rig_name(rig)) from None


def rig_for_scene(scene_path: str) -> RigModelFiles:
    """The rig whose scene a package-relative scene path names (an execution snapshot records `scene_path`)."""
    for files in RIG_MODEL_FILES.values():
        if files.scene == scene_path:
            return files
    raise ValueError("RIG_SCENE_UNKNOWN: " + str(scene_path))


def foreign_files(rig=None) -> frozenset:
    """Files that belong to another rig and are not this rig's (excluded from this rig's profile identity digest).

    The side+wrist indoor rig shares the robot, URDF, plugin and controller files of `side-wrist`: they are in both rigs' own sets, so
    neither leaves them out, while the indoor scenes are foreign to `head-wrist` and `side-wrist` (their identity digests are those
    they had before the indoor rig existed) and the `side-wrist` scene is foreign to the indoor rig."""
    own = rig_model_files(rig)
    return frozenset(path for files in RIG_MODEL_FILES.values() if files is not own for path in files.exclusive) - own.exclusive
