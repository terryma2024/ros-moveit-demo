from pathlib import Path
from xml.etree import ElementTree


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/scene.xml"
MULTI_OBJECT_SCENE = PACKAGE / "assets/mujoco/v5_multi_object_scene.xml"


def test_cup_test_keyframes_move_only_the_cup_free_joint() -> None:
    root = ElementTree.parse(SCENE).getroot()
    keyframes = {
        key.attrib["name"]: tuple(float(value) for value in key.attrib["qpos"].split())
        for key in root.findall("./keyframe/key")
    }

    expected_cup_poses = {
        "cup_test_forward_5cm": (0.02, -0.33, 0.165, 1.0, 0.0, 0.0, 0.0),
        "cup_test_left_5cm": (-0.03, -0.28, 0.165, 1.0, 0.0, 0.0, 0.0),
        "cup_test_right_5cm": (0.07, -0.28, 0.165, 1.0, 0.0, 0.0, 0.0),
    }

    for name, expected_cup_pose in expected_cup_poses.items():
        assert keyframes[name][:6] == (0.0,) * 6
        assert keyframes[name][6:] == expected_cup_pose


def test_multi_object_cup_test_keyframes_move_only_the_target_cup() -> None:
    root = ElementTree.parse(MULTI_OBJECT_SCENE).getroot()
    keyframes = {
        key.attrib["name"]: tuple(float(value) for value in key.attrib["qpos"].split())
        for key in root.findall("./keyframe/key")
    }
    task_start = keyframes["task_start"]
    expected_cup_poses = {
        "cup_test_forward_5cm": (0.02, -0.33, 0.165, 1.0, 0.0, 0.0, 0.0),
        "cup_test_left_5cm": (-0.03, -0.28, 0.165, 1.0, 0.0, 0.0, 0.0),
        "cup_test_right_5cm": (0.07, -0.28, 0.165, 1.0, 0.0, 0.0, 0.0),
    }

    for name, expected_cup_pose in expected_cup_poses.items():
        assert keyframes[name][:6] == (0.0,) * 6
        assert keyframes[name][6:13] == expected_cup_pose
        assert keyframes[name][13:] == task_start[13:]
