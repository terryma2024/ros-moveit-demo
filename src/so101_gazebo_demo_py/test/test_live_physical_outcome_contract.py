from pathlib import Path
import math
import pytest
from types import SimpleNamespace

from so101_gazebo_demo_py.live_execute import (
    _stable_bilateral, carry_with_shadow_gates, compose_pose,
    plan_waypoint_sequence, relative_pose, rotated_grasp_pose,
    run_bounded_physical_grasp_attempts, shadow_divergence_healthy,
    seat_and_stabilize_physical_grasp,
    synchronize_planning_shadow,
    translated_grasp_pose,
)
from so101_gazebo_demo_py.gazebo.observer import ContactPair
from so101_gazebo_demo_py.policy_config import PlanningShadowConfig
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import (
    close_gazebo_subscription, closest_pose_pair, coobserved_tcp_sample,
    parse_model_pose, parse_tf_pose,
    pose_pair_ready, sample_pose_pair_with_retry,
    select_gazebo_pose, select_stamped_transform,
)


PACKAGE = Path(__file__).parents[1]
LIVE_EXECUTE = PACKAGE / "so101_gazebo_demo_py/live_execute.py"
MOTION_POLICY = PACKAGE / "config/motion_policies/light_cup_wall_pick.yaml"
LIVE_CLI = PACKAGE / "so101_gazebo_demo_py/cli/pick_place_state_machine.py"
ROS_GAZEBO_BACKEND = PACKAGE / "so101_gazebo_demo_py/test_support/ros_gazebo_backend.py"


def test_live_forward_path_never_commands_gazebo_attachment() -> None:
    source = LIVE_EXECUTE.read_text()
    assert ".set_attached(" not in source
    assert '"ATTACH_GAZEBO"' not in source
    assert '"DETACH_GAZEBO"' not in source
    assert '"physical-failure.json"' in source


def test_live_path_normalizes_approved_penetration_target_before_carry() -> None:
    source = LIVE_EXECUTE.read_text()
    live_path = source[source.index("def run_live_execute") :]
    assert "tune_seating_penetration(" not in live_path
    assert "stabilize_to_target_penetration(" in live_path
    assert "minimum_penetration_m: float = 0.0001" in source
    assert "maximum_penetration_m: float = 0.001" in source
    assert '"normalized_target_q6":normalized_seating_target' in live_path
    assert "moving-pad penetration ceiling exceeded" in source


def test_grasp_tcp_translation_occurs_before_physical_close() -> None:
    source = LIVE_EXECUTE.read_text()
    assert "_moveit_plan_grasp_translation" in source
    assert 'state.value == "DESCEND"' in source
    assert source.index("grasp_tcp_translation_offset_m") < source.index(
        "backend.move_gripper(close_target)"
    )


def test_grasp_tcp_translation_preserves_orientation() -> None:
    baseline = (0.02, -0.262, 0.201, 0.1, 0.2, 0.3, 0.9)
    assert translated_grasp_pose(baseline, (-0.0005, 0.0, 0.0)) == (
        0.0195, -0.262, 0.201, 0.1, 0.2, 0.3, 0.9,
    )


def test_grasp_world_x_rotation_changes_only_orientation() -> None:
    baseline = (0.02, -0.262, 0.201, 0.0, 0.0, 0.0, 1.0)
    rotated = rotated_grasp_pose(baseline, -0.017453292519943295)
    assert rotated[:3] == baseline[:3]
    half = -0.017453292519943295 / 2.0
    assert rotated[3:] == pytest.approx((math.sin(half), 0.0, 0.0, math.cos(half)))
    assert rotated_grasp_pose(baseline, 0.0) == baseline


def test_live_cli_forwards_selected_motion_policy() -> None:
    source = LIVE_CLI.read_text()
    assert "motion_policy=options.motion_policy" in source


def test_live_release_order_and_physical_outcome_states_are_explicit() -> None:
    source = LIVE_EXECUTE.read_text()
    assert source.index('"OPEN_GRIPPER"') < source.index('"RETREAT"')
    assert source.index('"RETREAT"') < source.index('"DETACH_MOVEIT"')
    assert '"WAIT_RELEASE_SETTLE"' in source
    assert '"VALIDATE_FINAL_PLACEMENT"' in source
    assert "time.sleep(2.)" not in source


def test_final_epoch_uses_one_observer_with_bounded_evidence_wait() -> None:
    live_source = LIVE_EXECUTE.read_text()
    live_path = live_source[live_source.index("def run_live_execute") :]
    assert live_path.count("with backend.final_observer() as final_observer:") == 1
    assert live_path.index("with backend.final_observer() as final_observer:") < (
        live_path.index("return collect_final_outcome_epoch(")
    )
    assert live_path.index("return collect_final_outcome_epoch(") < (
        live_path.index("outcomes=collect_final_outcome_after_immediate_retreat(")
    )
    backend_source = ROS_GAZEBO_BACKEND.read_text()
    assert "deadline=time.monotonic()+3.0" in backend_source
    assert "self._context=rclpy.Context()" in backend_source
    assert "context=self._context" in backend_source
    assert "SingleThreadedExecutor(context=self._context)" in backend_source
    assert "self._executor.add_node(self._node)" in backend_source
    assert "self._executor.spin_once(timeout_sec=0.02)" in backend_source
    assert "self._executor.remove_node(self._node)" in backend_source
    assert "self._executor.shutdown()" in backend_source
    assert "self._context.shutdown()" in backend_source
    assert "pose_pair_ready(observed,self._max_pair_age_s)" in backend_source
    assert "self._contacts.fresh(time.monotonic(),1.0)" in backend_source


def test_transient_empty_pose_pair_retries_one_fresh_subscription() -> None:
    expected = SimpleNamespace(object_xyz=(0.0, 0.0, 0.165))
    attempts = []

    def sample_once():
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise RuntimeError(
                "fresh Gazebo/TCP pose pair unavailable: "
                "{'object': None, 'tcp': None}"
            )
        return expected

    assert sample_pose_pair_with_retry(sample_once) is expected
    assert attempts == [1, 2]


def test_pose_pair_retry_remains_bounded_after_two_empty_subscriptions() -> None:
    attempts = []

    def sample_once():
        attempts.append(len(attempts) + 1)
        raise RuntimeError(
            "fresh Gazebo/TCP pose pair unavailable: "
            "{'object': None, 'tcp': None}"
        )

    with pytest.raises(RuntimeError, match="fresh Gazebo/TCP pose pair unavailable"):
        sample_pose_pair_with_retry(sample_once)

    assert attempts == [1, 2]


def test_moveit_shadow_attach_requires_authoritative_gazebo_pose() -> None:
    source = LIVE_EXECUTE.read_text()
    assert 'operation == "attach"' in source
    assert "object_pose is None" in source
    assert "object_pose[:3]" in source


def test_live_run_reuses_one_isolated_planning_scene_client() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def run_live_execute"):]

    assert "class PlanningSceneShadowClient:" in source
    assert "self._context=rclpy.Context()" in source
    assert "SingleThreadedExecutor(context=self._context)" in source
    assert "with PlanningSceneShadowClient() as scene_client:" in forward_path
    assert "apply_scene=scene_client.apply" in forward_path
    assert "apply_scene(\"attach\",shadow_pose)" in source
    assert 'apply_scene("detach",retreated_pose)' in source
    assert "detach_and_sync(released)" not in source
    assert "_apply_scene(" not in forward_path


def test_moveit_shadow_attach_precedes_physical_micro_lift_planning() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def run_live_execute"):]

    assert forward_path.index('attached_scene=apply_scene("attach"') < (
        forward_path.index("run_bounded_physical_grasp_attempts(")
    )
    assert ".set_attached(" not in forward_path


def test_live_path_retries_one_failed_micro_lift_at_requested_preload() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def run_live_execute"):]
    grasp_call = forward_path[
        forward_path.index("run_bounded_physical_grasp_attempts("):
        forward_path.index("except Exception as error:", forward_path.index(
            "run_bounded_physical_grasp_attempts("
        ))
    ]

    assert "max_grasp_attempts=2" in forward_path
    assert "max_attempts=max_grasp_attempts" in grasp_call
    assert "seating_actual_q6=_current_joint_position(\"6\")" in forward_path
    assert "seating_target=_current_joint_position(\"6\")" not in forward_path
    assert '"actual_q6":seating_actual_q6' in forward_path


def test_every_release_path_retreats_before_scene_detach_and_settle() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def _run_live_execute_with_scene"):]

    release_index = forward_path.index(
        "backend.move_gripper(bundle.motion.release_q6, final_release=True)"
    )
    retreat_definition = forward_path.index("def immediate_retreat():", release_index)
    immediate_index = forward_path.index(
        "collect_final_outcome_after_immediate_retreat(", retreat_definition,
    )
    detach_index = forward_path.index(
        'apply_scene("detach",retreated_pose)', retreat_definition,
    )

    assert forward_path.index("align_cup_for_release(") < release_index
    assert release_index < retreat_definition < immediate_index
    assert forward_path.index("backend.move_arm(", retreat_definition) < detach_index
    assert detach_index < immediate_index
    assert "if not place_alignment:" not in forward_path
    assert "detach_and_sync(released)" not in forward_path
    assert "return FinalOutcomeEpochs(None,collect_epoch())" in source


def test_live_alignment_uses_six_mm_tolerance_and_fixed_retreat() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def _run_live_execute_with_scene"):]

    alignment_start = forward_path.index(
        "placed,_place_reverse_waypoints,place_alignment="
    )
    alignment_call = forward_path[
        alignment_start:
        forward_path.index(
            "backend.move_gripper(bundle.motion.release_q6", alignment_start,
        )
    ]
    assert "xy_tolerance_m=0.006" in alignment_call
    assert "collect_final_outcome_after_immediate_retreat(" in forward_path
    assert "collect_final_outcomes_around_retreat(" not in forward_path


def test_no_alignment_retreat_uses_explicit_fast_policy_scaling() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def run_live_execute"):]
    retreat = MOTION_POLICY.read_text().split("  RETREAT:", 1)[1].split(
        "  RECOVER_LIFT_TO_SAFE_HEIGHT:", 1,
    )[0]

    assert (
        "backend.move_arm(retreat_policy.waypoints, "
        "velocity_scaling=retreat_policy.velocity_scaling)"
    ) in forward_path
    assert "velocity_scaling: 0.10" in retreat


def test_shadow_divergence_gate_fails_closed_on_each_bound_and_age() -> None:
    policy = PlanningShadowConfig(0.005, 0.070, 0.10)
    gazebo = (0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0)
    assert shadow_divergence_healthy(gazebo, gazebo, 0.01, policy)
    assert not shadow_divergence_healthy(
        gazebo, (0.006, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0), 0.01, policy,
    )
    tilted = (0.0, 0.0, 0.2, math.sin(0.08 / 2), 0.0, 0.0, math.cos(0.08 / 2))
    assert not shadow_divergence_healthy(gazebo, tilted, 0.01, policy)
    assert not shadow_divergence_healthy(gazebo, gazebo, 0.11, policy)


def test_fresh_physical_slip_resynchronizes_moveit_shadow() -> None:
    observed = SimpleNamespace(
        object_xyz=(0.010, 0.0, 0.2),
        object_xyzw=(0.0, 0.0, 0.0, 1.0),
        tcp_xyz=(0.0, 0.0, 0.3),
        tcp_xyzw=(0.0, 0.0, 0.0, 1.0),
        pose_pair_age_s=0.01,
    )
    applied = []

    check, object_in_tcp = synchronize_planning_shadow(
        SimpleNamespace(sample=lambda: observed),
        (0.0, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0),
        PlanningShadowConfig(0.005, 0.070, 0.10),
        apply_scene=lambda operation, pose: (
            applied.append((operation, pose))
            or {"world_objects": [], "attached_objects": ["plastic_cup"]}
        ),
    )

    assert check["healthy_before_sync"] is False
    assert check["resynchronized"] is True
    assert applied == [("attach", (0.010, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0))]
    assert compose_pose(
        (*observed.tcp_xyz, *observed.tcp_xyzw), object_in_tcp,
    ) == pytest.approx((*observed.object_xyz, *observed.object_xyzw))


def test_shadow_gate_can_reuse_a_persistent_pose_observer() -> None:
    observed = SimpleNamespace(
        object_xyz=(0.0, 0.0, 0.2),
        object_xyzw=(0.0, 0.0, 0.0, 1.0),
        tcp_xyz=(0.0, 0.0, 0.3),
        tcp_xyzw=(0.0, 0.0, 0.0, 1.0),
        pose_pair_age_s=0.01,
    )
    calls = []

    check, _ = synchronize_planning_shadow(
        SimpleNamespace(sample=lambda: pytest.fail("one-shot observer recreated")),
        (0.0, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0),
        PlanningShadowConfig(0.005, 0.070, 0.10),
        apply_scene=lambda *_: pytest.fail("healthy shadow must not resync"),
        observe_pose=lambda: calls.append("persistent") or observed,
    )

    assert calls == ["persistent"]
    assert check["healthy_before_sync"] is True


def test_stale_physical_pose_cannot_resynchronize_moveit_shadow() -> None:
    observed = SimpleNamespace(
        object_xyz=(0.010, 0.0, 0.2),
        object_xyzw=(0.0, 0.0, 0.0, 1.0),
        tcp_xyz=(0.0, 0.0, 0.3),
        tcp_xyzw=(0.0, 0.0, 0.0, 1.0),
        pose_pair_age_s=0.11,
    )

    with pytest.raises(RuntimeError, match="planning shadow evidence stale"):
        synchronize_planning_shadow(
            SimpleNamespace(sample=lambda: observed),
            (0.0, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0),
            PlanningShadowConfig(0.005, 0.070, 0.10),
            apply_scene=lambda operation, pose: pytest.fail(
                "stale evidence must not update the Planning Scene"
            ),
        )


def test_gazebo_model_pose_preserves_authoritative_orientation() -> None:
    pose = parse_model_pose(
        "position [1.0 -2.0 0.3]\norientation [0.0 0.0 1.5707963267948966]"
    )
    assert pose[:3] == (1.0, -2.0, 0.3)
    assert pose[3:] == pytest.approx((0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)))


def test_relative_shadow_pose_round_trips_through_latest_tcp_pose() -> None:
    tcp = (0.1, -0.2, 0.3, 0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5))
    cup = (0.12, -0.19, 0.28, 0.0, 0.0, 0.0, 1.0)
    assert compose_pose(tcp, relative_pose(tcp, cup)) == pytest.approx(cup)


def test_every_carry_motion_is_preceded_by_shadow_gate() -> None:
    calls = []
    policies = {
        name: SimpleNamespace(waypoints=index, velocity_scaling=0.1)
        for index, name in enumerate(("LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE"))
    }

    class Backend:
        def move_arm(self, waypoints, velocity=None):
            calls.append(("move", waypoints, velocity))

    carry_with_shadow_gates(Backend(), policies, lambda name: calls.append(("gate", name)))
    assert calls[::2] == [("gate", name) for name in policies]
    assert calls[1::2] == [
        ("move", index, 0.1) for index in range(len(policies))
    ]


def test_live_carry_reuses_one_persistent_observer_for_all_shadow_gates() -> None:
    source = LIVE_EXECUTE.read_text()
    forward_path = source[source.index("def run_live_execute"):]
    carry_start = forward_path.index("with backend.final_observer() as carry_observer:")
    carry_end = forward_path.index("target_place_xyz=", carry_start)
    carry_path = forward_path[carry_start:carry_end]

    assert carry_path.count("carry_observer.observe()[0]") == 1
    assert "carry_with_shadow_gates(" in carry_path
    assert carry_path.index("carry_observer.observe()[0]") < carry_path.index(
        "carry_with_shadow_gates("
    )


def test_tcp_pose_parser_requires_translation_and_quaternion() -> None:
    output = "Translation: [0.1, -0.2, 0.3]\nRotation: in Quaternion [0.0, 0.0, 0.0, 1.0]"
    assert parse_tf_pose(output) == (0.1, -0.2, 0.3, 0.0, 0.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        parse_tf_pose("Translation: [0.1, -0.2, 0.3]")


def test_stamped_transform_selector_preserves_source_timestamp() -> None:
    transform = SimpleNamespace(
        child_frame_id="plastic_cup",
        header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=500_000_000)),
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=1.0, y=2.0, z=3.0),
            rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
    )
    assert select_stamped_transform([transform], "plastic_cup") == (
        (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0), 12.5,
    )
    assert select_stamped_transform([transform], "so101_tcp") is None


def test_gazebo_pose_selector_uses_entity_name_and_source_timestamp() -> None:
    pose = SimpleNamespace(
        name="plastic_cup",
        position=SimpleNamespace(x=1.0, y=2.0, z=3.0),
        orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    message = SimpleNamespace(
        pose=[pose],
        header=SimpleNamespace(stamp=SimpleNamespace(sec=20, nsec=250_000_000)),
    )
    assert select_gazebo_pose(message, "plastic_cup") == (
        (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0), 20.25,
    )
    assert select_gazebo_pose(message, "other") is None

    pose.position.x = float("nan")
    assert select_gazebo_pose(message, "plastic_cup") is None


def test_gazebo_pose_subscription_is_explicitly_closed() -> None:
    calls = []
    node = SimpleNamespace(unsubscribe=lambda topic: calls.append(topic))

    close_gazebo_subscription(node, "/world/example/pose/info")

    assert calls == ["/world/example/pose/info"]


def test_pose_pair_waits_for_configured_source_timestamp_freshness() -> None:
    observed = {
        "object": ((0.0,) * 7, 10.0),
        "tcp": ((0.0,) * 7, 10.11),
    }
    assert not pose_pair_ready(observed, 0.10)

    observed["object"] = ((0.0,) * 7, 10.02)
    assert pose_pair_ready(observed, 0.10)


def test_closest_pose_pair_retains_cross_source_history() -> None:
    object_samples = [((1.0,) * 7, 10.0), ((2.0,) * 7, 10.2)]
    tcp_samples = [((3.0,) * 7, 9.89), ((4.0,) * 7, 10.09)]

    pair = closest_pose_pair(object_samples, tcp_samples)

    assert pair == {
        "object": ((1.0,) * 7, 10.0),
        "tcp": ((4.0,) * 7, 10.09),
    }


def test_closest_pose_pair_snapshots_under_shared_callback_lock() -> None:
    class Lock:
        def __init__(self):
            self.entries = 0

        def __enter__(self):
            self.entries += 1

        def __exit__(self, *_args):
            return False

    lock = Lock()
    pair = closest_pose_pair(
        [((1.0,) * 7, 10.0)],
        [((2.0,) * 7, 10.01)],
        lock=lock,
    )

    assert lock.entries == 1
    assert pair["object"][1] == 10.0
    assert pair["tcp"][1] == 10.01


def test_static_tf_is_stamped_at_the_coobserved_gazebo_pose() -> None:
    tcp_pose = (2.0,) * 7
    object_samples = [((1.0,) * 7, 10.2)]

    assert coobserved_tcp_sample(tcp_pose, 9.7, object_samples) == (
        tcp_pose, 10.2,
    )
    assert coobserved_tcp_sample(tcp_pose, 9.7, ()) == (tcp_pose, 9.7)


def test_plan_only_validates_every_waypoint_as_a_contiguous_sequence() -> None:
    requests = []
    class Planner:
        def plan_joint_path(self, request, timeout):
            requests.append((request, timeout))
            return SimpleNamespace(
                failure=None,
                trajectory=SimpleNamespace(
                    joint_trajectory=SimpleNamespace(points=[object(), object()]),
                ),
            )
    points = plan_waypoint_sequence(
        Planner(), ("1", "2"), (0.0, 0.0), ((0.1, 0.2), (0.3, 0.4)),
    )
    assert points == 4
    assert requests[0][0].current_positions == (0.0, 0.0)
    assert requests[0][0].target_positions == requests[1][0].current_positions == (0.1, 0.2)
    assert requests[1][0].target_positions == (0.3, 0.4)


def test_calibration_candidate_stops_after_first_cup_outcome_failure() -> None:
    calls = []

    class Backend:
        def contacts(self):
            calls.append("contacts")
            return ()

        def sample(self):
            calls.append("sample")
            return SimpleNamespace(
                object_xyz=(0.0, 0.0, 0.165),
                tcp_xyz=(0.0, 0.0, 0.2),
                tcp_xyzw=(0.0, 0.0, 0.0, 1.0),
            )

        def move_gripper(self, value):
            calls.append(("gripper", value))

    with pytest.raises(RuntimeError, match="CUP_INSUFFICIENT_LIFT"):
        run_bounded_physical_grasp_attempts(
            Backend(), -0.053, 0.465, -0.0596, max_attempts=1,
            execute=lambda delta: calls.append(("move", delta)) or (3, 0.2),
        )
    assert calls.count(("move", 0.002)) == 1
    assert not any(isinstance(value, tuple) and value[0] == "gripper" for value in calls)


def test_stable_bilateral_fails_immediately_on_moving_pad_hard_ceiling() -> None:
    contacts = (
        ContactPair("plastic_cup::body::wall_near", "fixed_fingertip_pad_collision_001", (0.0004,)),
        ContactPair("plastic_cup::body::wall_near", "moving_fingertip_pad_collision_001", (0.001300001,)),
    )
    backend = SimpleNamespace(contacts=lambda: contacts)

    with pytest.raises(RuntimeError, match="moving-pad penetration ceiling exceeded"):
        _stable_bilateral(backend)


def test_seating_preload_waits_for_stable_bilateral_contact() -> None:
    calls = []
    contacts = (
        ContactPair(
            "plastic_cup::body::wall_near",
            "fixed_fingertip_pad_collision_001",
            (0.0004,),
        ),
        ContactPair(
            "plastic_cup::body::wall_near",
            "moving_fingertip_pad_collision_001",
            (0.0008,),
        ),
    )

    class Backend:
        def move_gripper(self, target):
            calls.append(("gripper", target))

        def contacts(self):
            calls.append("contacts")
            return contacts

    result = seat_and_stabilize_physical_grasp(Backend(), -0.0515)

    assert result.bilateral
    assert result.max_moving_pad_penetration_m == pytest.approx(0.0008)
    assert calls[0] == ("gripper", -0.0515)
    assert calls.count("contacts") == 6
