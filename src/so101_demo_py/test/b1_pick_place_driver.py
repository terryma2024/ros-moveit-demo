"""Fixture driver for B1: one full collection-off pick-place through MoveIt ExecuteTrajectory + JTC fakes.

Not a test module (no `test_` prefix). `run(tmp_path)` constructs the real `RosDynamicMujocoExecution` over a fake ROS
node, with `rclpy.action.ActionClient` replaced by a fake that serves `/execute_trajectory` and the gripper's
`/gripper_controller/follow_joint_trajectory` from a tiny world model, and runs the real `StateMachineRunner` over
`build_dynamic_actions`. Planning, IK and the MoveIt scene services are the only stubs; the clients, the monitor, the
stop proof and the release path are the production code.

`python -c "import b1_pick_place_driver as d; ..."` is how the sys.modules test uses it, in a clean interpreter.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

PACKAGE = Path(__file__).resolve().parents[1]
ARM = ("1", "2", "3", "4", "5")
REST_Z = 0.165

BROKER_STEMS = frozenset({
    "command_broker", "ros_broker", "broker_execution", "broker_authority_composition", "broker_authority_wiring",
    "controller_reservation_client", "controller_reservation_provision", "dispatch_transaction",
    "visible_approach_commit_ingress", "ros_controller_port", "leased_action_client", "act_command_broker",
    "teacher_native_forward", "teacher_native_runtime", "teacher_native_reconstruction", "teacher_native_path_safety",
    "native_controller_context", "native_process_provenance", "native_trajectory_sampler", "teacher_bound_authority",
    "teacher_bound_timing", "teacher_owner_peer", "teacher_physics_source", "ros_teacher_physics_source",
    "teacher_point_of_use", "controller_initial_empty_observation", "controller_retirement_observation",
    "teacher_forward_diagnostics", "teacher_goal_capture", "teacher_trajectory", "teacher_reset_binding",
    "teacher_initial_empty_reset", "teacher_episode_binding", "teacher_coordinator_receipt",
    "teacher_phase_lifecycle", "native_dispatch", "native_stop", "broker_stop_policy",
    "act_first_episode_composition", "teacher_worker_lifecycle", "teacher_cup_safety", "teacher_table_support",
})


def broker_modules_loaded():
    import sys

    return sorted(name for name in sys.modules if name.rsplit(".", 1)[-1] in BROKER_STEMS)


class Future:
    def __init__(self, value=None, done=True):
        self._value, self._done = value, done

    def done(self):
        return self._done

    def result(self):
        return self._value

    def finish(self, value):
        self._value, self._done = value, True


class World:
    """Joint positions, the cup and the controllers: advanced one step per `rclpy.spin_once`."""

    def __init__(self):
        self.positions = {**{name: 0.0 for name in ARM}, "6": 0.465}
        self.velocities = {name: 0.0 for name in (*ARM, "6")}
        self.cup_lift = 0.0
        self.step = 1000
        self.sequence = 1000
        self.pending = []  # [steps_left, apply_callable, handle]
        self.execute_goals, self.gripper_goals, self.cancels = [], [], []
        self.execution = None
        self.timeline = []

    # ---- the fake controllers --------------------------------------------------------------------------------
    def goal(self, kind, target, apply):
        handle = Handle(self)
        self.pending.append([3, apply, handle, kind])
        for name in self.velocities:
            self.velocities[name] = 0.1
        return handle

    def advance(self):
        for item in list(self.pending):
            item[0] -= 1
            if item[0] <= 0:
                item[1]()
                item[2].finish(item[3])
                self.pending.remove(item)
        if not self.pending:
            for name in self.velocities:
                self.velocities[name] = 0.0

    # ---- evidence --------------------------------------------------------------------------------------------
    def closed(self):
        return self.positions["6"] <= 0.0

    def evidence(self):
        from so101_demo.core.simulation.types import ContactEvidence, ObjectState, SimulationEvidence

        def contact(body2, geom2, force, distance):
            return ContactEvidence(12, 93, "plastic_cup", "bottom_collision", 7, 70, body2, geom2,
                                   (0.0, 0.0, 0.1), (0.0, 0.0, 1.0), distance, force)

        resting = self.cup_lift < 0.002
        left = (contact("gripper", "fixed_fingertip_pad_collision_006", 0.22, -3e-5),) if self.closed() and not self.opened_after_release else ()
        right = (contact("jaw", "moving_fingertip_pad_collision_000", 0.23, -3e-5),) if self.closed() and not self.opened_after_release else ()
        other = (contact("table", "table_collision", 0.2, -5e-5),) if resting else ()
        every = left + right + other
        self.step += 1
        self.sequence += 1
        return SimulationEvidence(
            simulation_time_s=self.step * 0.002, frame_id="world", publisher_sequence=self.sequence,
            simulation_step=self.step, reset_epoch=1, simulation_session_id="s", paused=False,
            object_state=ObjectState(12, "plastic_cup", (0.02, -0.28, REST_Z + self.cup_lift), (0.0, 0.0, 0.0, 1.0),
                                     (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            has_contact=bool(every), minimum_signed_distance_m=min((c.signed_distance_m for c in every), default=0.0),
            maximum_normal_force_n=max((c.normal_force_n for c in every), default=0.0), truncated=False,
            left_fingertip_contacts=left, right_fingertip_contacts=right, other_object_contacts=other)

    opened_after_release = False


class Handle:
    accepted = True

    def __init__(self, world):
        self._world = world
        self.result_future = Future(done=False)

    def finish(self, kind):
        code = SimpleNamespace(val=1) if kind == "arm" else 0
        self.result_future.finish(SimpleNamespace(result=SimpleNamespace(error_code=code)))

    def get_result_async(self):
        return self.result_future

    def cancel_goal_async(self):
        self._world.cancels.append(self)
        return Future("cancelled")


def make_action_client_class(world):
    class ActionClient:
        def __init__(self, node, action_type, action_name):
            self.name = action_name

        def wait_for_server(self, timeout_sec=None):
            return True

        def send_goal_async(self, goal):
            world.timeline.append(("goal", self.name, time.monotonic_ns()))
            if self.name == "/execute_trajectory":
                points = goal.trajectory.joint_trajectory.points
                final = [float(value) for value in points[-1].positions]
                world.execute_goals.append(goal)

                def apply():
                    world.positions.update(dict(zip(ARM, final, strict=True)))
                    state = getattr(world.execution, "_scene_state_value", None)
                    world.cup_lift = {"MICRO_LIFT": 0.003, "LIFT": 0.10, "MOVE_ABOVE_PLACE": 0.10,
                                      "DESCEND_TO_PLACE": 0.0}.get(state, world.cup_lift)
                return Future(world.goal("arm", final, apply))
            target = float(goal.trajectory.points[-1].positions[0])
            world.gripper_goals.append(target)

            def apply():
                world.positions["6"] = target
                if target > 0.7:
                    world.opened_after_release = True
                elif target < 0.0:
                    world.opened_after_release = False
            return Future(world.goal("gripper", target, apply))

    return ActionClient


class FakeNode:
    def __init__(self):
        self.subscriptions, self.clients = [], []

    def create_subscription(self, *args, **kwargs):
        self.subscriptions.append(args[1] if len(args) > 1 else None)
        return SimpleNamespace(get_publisher_count=lambda: 1)

    def create_client(self, *args, **kwargs):
        self.clients.append(args)
        return SimpleNamespace(wait_for_service=lambda **_kw: True)

    def destroy_subscription(self, _value):
        return True

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=time.monotonic_ns()))


class FakeStream:
    def __init__(self):
        self.events = []

    def offer(self, kind, payload=None):
        self.events.append((kind, payload))
        return True

    def snapshot(self):
        return {"events": len(self.events)}

    def close(self, flush_timeout_s=1.0):
        return True


class FakeIk:
    def forward(self, joints):
        from so101_demo.ports.evidence import PoseEvidence
        return PoseEvidence(tuple(float(v) for v in joints[:3]), (0.0, 0.0, 0.0, 1.0))

    @staticmethod
    def orientation_error_rad(_a, _b):
        return 0.0


class FakeObserver:
    def __init__(self, world, execution_ref):
        self.world, self.latest, self.history = world, None, []

    def pump(self):
        sample = self.world.evidence()
        received = time.monotonic()
        from so101_demo.core.simulation.types import ReceivedSimulationEvidence
        self.latest = ReceivedSimulationEvidence(sample, received)
        self.history = (self.history + [self.latest])[-20:]
        return sample, received

    def snapshot_with_receipt(self):
        from so101_demo.backends.mujoco.observer import EvidenceStale
        if self.latest is None or time.monotonic() - self.latest.received_monotonic_s > 0.5:
            raise EvidenceStale("stale")
        return self.latest

    def snapshot(self):
        return self.snapshot_with_receipt().evidence

    def recent_with_receipts(self):
        return tuple(self.history)


def run(tmp_path, *, with_collection_port_env=False, event_stream=None):
    import rclpy
    import rclpy.action
    from so101_demo.application.dynamic_execute import build_dynamic_actions
    from so101_demo.core.domain import RunMode, RunRequest
    from so101_demo.core.dynamic_pick import resolve_motion_targets
    from so101_demo.core.runner import StateMachineRunner
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    from test_dynamic_pick import _sample, _template
    from moveit_msgs.msg import RobotTrajectory
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    world = World()
    template, sample = _template(), _sample()
    targets = resolve_motion_targets(sample, template)
    saved_client, saved_spin = rclpy.action.ActionClient, rclpy.spin_once
    rclpy.action.ActionClient = make_action_client_class(world)
    node, stream = FakeNode(), (FakeStream() if event_stream is None else event_stream)
    try:
        execution = RosDynamicMujocoExecution(
            node, template, targets, session_id="s", expected_reset_epoch=1,
            evidence_file=Path(tmp_path) / "dynamic-execute-manifest.json",
            urdf_path=PACKAGE / "assets/mujoco/so101.urdf", policy_path=Path("policy.yaml"), policy_sha256="a" * 64,
            event_stream=stream)
    finally:
        rclpy.action.ActionClient = saved_client
    world.execution = execution
    observer = FakeObserver(world, execution)
    execution.observer = observer
    scene = SceneStateObserver(model_sha256="a" * 64, nq=1, nv=1, max_age_s=0.5, monotonic=time.monotonic)
    scene.reset("s", 1, source_floor_s=0.0)
    execution._scene_source_observer = scene
    execution._ik = FakeIk()
    execution._attempt_id = "attempt-1"

    def spin(_node, timeout_sec=0.0):
        time.sleep(0.002)
        world.advance()
        sample_, received = observer.pump()
        stamp_ns = round(sample_.simulation_time_s * 1e9)
        execution._on_joint_state(SimpleNamespace(
            name=[*ARM, "6"], position=[world.positions[n] for n in (*ARM, "6")],
            velocity=[world.velocities[n] for n in (*ARM, "6")],
            header=SimpleNamespace(stamp=SimpleNamespace(sec=stamp_ns // 10**9, nanosec=stamp_ns % 10**9))))
        end = round((received - 0.0005) * 1e9)
        scene.accept({"simulation_session_id": "s", "reset_epoch": 1, "simulation_step": sample_.simulation_step,
                      "paused": False, "simulation_time_s": sample_.simulation_time_s, "model_sha256": "a" * 64,
                      "qpos": [0.0], "qvel": [0.0], "clock_interval_begin_monotonic_ns": end - 1_000_000,
                      "clock_interval_end_monotonic_ns": end})

    rclpy.spin_once = spin
    execution._teacher_endpoint_policy = None  # no endpoint judgement in this fixture (legacy partial construction)

    def plan(request, timeout_s=None):
        points = [JointTrajectoryPoint(positions=[float(v) for v in request.current_positions]),
                  JointTrajectoryPoint(positions=[float(v) for v in request.target_positions])]
        trajectory = RobotTrajectory(joint_trajectory=JointTrajectory(joint_names=list(ARM), points=points))
        return SimpleNamespace(failure=None, trajectory=trajectory)

    execution._planning = SimpleNamespace(plan_joint_path=plan)

    def horizon(state, motion_targets, current):
        joint_target = tuple(value + (0.01 if index == 2 else 0.0) for index, value in enumerate(current))
        target = motion_targets[-1]
        receipt = SimpleNamespace(joint_positions_rad=joint_target, to_document=lambda: {})
        return (SimpleNamespace(waypoint=SimpleNamespace(target=target, state=state, segment_index=0),
                                receipt=receipt),)

    execution._motion_horizon = horizon
    execution._plan_candidate_set = lambda *, state, step, current, joint_target: (
        plan(SimpleNamespace(current_positions=current, target_positions=joint_target)), [])
    execution._set_touch_collision = lambda allowed: None
    execution._scene_membership = lambda: ([], {})
    execution._confirm_detached_shadow = lambda: True

    def attach(state):
        snapshot = execution._snapshot()
        execution._attached = True
        execution._record(state, snapshot, snapshot)

    def detach(state):
        from so101_demo.core.domain import State
        before = (execution._supported_release_preflight()
                  if state in (State.DETACH_MOVEIT, State.RECOVER_DETACH_MOVEIT) else execution._snapshot())
        execution._attached = False
        execution._release_scene_geometry = object()
        execution._record(state, before, before)

    execution._attach, execution._detach_or_sync = attach, detach
    try:
        runner = StateMachineRunner(build_dynamic_actions(execution, targets), session_id="s",
                                    policy_bundle_sha256="a" * 64, world_observer=observer)
        result = runner.run(RunRequest(mode=RunMode.EXECUTE))
        execution.finish(result)
    finally:
        rclpy.spin_once = saved_spin
    return SimpleNamespace(result=result, world=world, execution=execution, events=getattr(stream, 'events', []), node=node)
