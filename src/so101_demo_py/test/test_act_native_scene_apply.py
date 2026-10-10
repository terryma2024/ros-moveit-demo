"""Exercise generated requests through the installed native MoveIt library, without ROS services."""

import json
import shutil
import subprocess

import pytest

from test_act_scene_association import frozen_scene
from test_act_scene_attachment_association import attachment
from paths import TEST_ROOT


@pytest.fixture(scope="module")
def native_scene_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-scene-probe")
    cmake = shutil.which("cmake")
    assert cmake is not None
    source = TEST_ROOT / "native_scene_probe"
    for name, command in (("configure", [cmake, "-S", str(source), "-B", str(root / "build")]),
                          ("build", [cmake, "--build", str(root / "build"), "--parallel", "2"])):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        (root / (name + ".log")).write_text(result.stdout + result.stderr)
        (root / (name + ".rc")).write_text(str(result.returncode))
        assert result.returncode == 0, result.stdout + result.stderr
    executable = root / "build/scene_apply_probe"
    assert executable.is_file()
    return executable


@pytest.mark.parametrize("redundant_removal", [False, True])
def test_the_teachers_plain_attachment_is_accepted_by_actual_moveit_and_a_redundant_removal_is_not(
        native_scene_probe, frozen_scene, tmp_path, redundant_removal):
    """Superseded: the geometry-carrying (source alignment) attach request is no longer sent by anything.

    The Teacher's one request is the plain attach. The native MoveIt library accepts it, removes the cup from the world and
    attaches it to the gripper with the declared touch links; it keeps its own local pose, which is not asserted here.
    A redundant world REMOVE beside the attach is still refused natively, which is why the request never carries one.
    """
    from moveit_msgs.msg import CollisionObject
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from rclpy.serialization import serialize_message, deserialize_message
    from so101_demo.act.scene_association import _world, decode_ros, source_geometry
    from so101_demo.core.task_geometry import load_task_geometry, Pose7
    from so101_demo.control.planning_scene.task_scene import (
        make_plain_attach_scene, make_task_scene, verify_task_scene)
    document, raw = attachment(frozen_scene)
    expected = source_geometry(load_task_geometry(frozen_scene[0] / "assets/common/geometry-manifest.yaml"),
                               _world(document["source"]["physics"]))
    initial = ApplyPlanningScene.Request(scene=make_task_scene(expected))
    request = decode_ros(ApplyPlanningScene.Request, document["apply"]["record"]["request"])
    assert request == ApplyPlanningScene.Request(scene=make_plain_attach_scene())
    assert request.scene.world.collision_objects == []
    if redundant_removal:
        remove = CollisionObject(id="plastic_cup", operation=CollisionObject.REMOVE)
        remove.header.frame_id = "world"
        request.scene.world.collision_objects = [remove]
    (tmp_path / "initial.cdr").write_bytes(serialize_message(initial))
    (tmp_path / "request.cdr").write_bytes(serialize_message(request))
    result = subprocess.run([str(native_scene_probe), str(tmp_path / "initial.cdr"), str(tmp_path / "request.cdr"),
                             str(tmp_path / "response.cdr")], capture_output=True, text=True, check=False)
    (tmp_path / "native-apply.log").write_text(result.stdout + result.stderr)
    (tmp_path / "native-apply.rc").write_text(str(result.returncode))
    assert result.returncode == int(redundant_removal), result.stdout + result.stderr
    assert "native_apply_accepted=" + str(int(not redundant_removal)) in result.stdout
    if redundant_removal:
        return
    observed = deserialize_message((tmp_path / "response.cdr").read_bytes(), GetPlanningScene.Response)
    local = Pose7.parse(document["expected"]["geometry"]["local_cup"]["pose"]["values"], "fixture.local")
    # The strict source alignment comparison (data side) still sees MoveIt's own local pose as a difference ...
    strict = verify_task_scene(observed.scene, expected, expected_cup_attachment="gripper",
                               expected_cup_local_pose=local, expected_touch_links=("gripper", "jaw"))
    assert strict.evidence["mismatches"] == ["plastic_cup.pose"], strict.evidence
    # ... but the broker's attached-phase proof treats the local pose as an audit diagnostic and PASSES, recording the delta.
    verified = verify_task_scene(observed.scene, expected, expected_cup_attachment="gripper",
                                 expected_cup_local_pose=local, expected_touch_links=("gripper", "jaw"),
                                 cup_local_pose_audit_only=True)
    assert verified.success and verified.evidence["mismatches"] == [], verified.evidence
    audit = verified.evidence["cup_local_pose_audit"]
    assert audit["refuses"] is False and audit["reason"] is None
    assert audit["translation_delta_m"] > 1e-6 or audit["rotation_delta_rad"] > 1e-6
    assert len(audit["expected_pose"]) == len(audit["observed_pose"]) == 7
    (tmp_path / "native-pose-delta.json").write_text(json.dumps(audit, sort_keys=True))
    assert verified.evidence["world_ids"] == ["pedestal", "table"]
    assert verified.evidence["attached_ids"] == ["plastic_cup"]
    assert verified.evidence["attached_links"] == {"plastic_cup": "gripper"}
