#!/usr/bin/env python3
"""Persistent ROS readiness probe for the headless Panda E2E test."""

import argparse
import json
import os
import time


class ReadinessTracker:
    REQUIRED_CONTROLLERS = (
        'joint_state_broadcaster',
        'panda_arm_controller',
        'panda_hand_controller',
    )

    def __init__(self):
        self._move_group = False
        self._arm_action_server = False
        self._hand_action_server = False
        self._controllers = {}
        self._joint_state = False
        self._planning_scene_coke = False
        self._completion_started = False
        self._emitted = set()

    def observe_nodes(self, names):
        self._move_group = '/move_group' in names

    def observe_action_servers(self, *, arm, hand):
        self._arm_action_server = arm
        self._hand_action_server = hand

    def observe_controllers(self, controllers):
        self._controllers = dict(controllers)

    def observe_joint_names(self, names):
        self._joint_state = 'panda_finger_joint1' in names

    def observe_scene_objects(self, object_ids):
        self._planning_scene_coke = 'coke' in object_ids

    def begin_completion_phase(self):
        self._completion_started = True
        self._joint_state = False
        self._planning_scene_coke = False

    def _core_ready(self):
        return (
            self._move_group
            and self._arm_action_server
            and self._hand_action_server
            and all(
                self._controllers.get(name) == 'active'
                for name in self.REQUIRED_CONTROLLERS
            )
        )

    def take_new_milestones(self):
        milestones = []
        if self._core_ready() and 'CORE_READY' not in self._emitted:
            self._emitted.add('CORE_READY')
            milestones.append('CORE_READY')
        if (
            self._core_ready()
            and self._completion_started
            and self._joint_state
            and self._planning_scene_coke
            and 'ALL_READY' not in self._emitted
        ):
            self._emitted.add('ALL_READY')
            milestones.append('ALL_READY')
        return milestones

    def snapshot(self):
        return {
            'move_group': self._move_group,
            'arm_action_server': self._arm_action_server,
            'hand_action_server': self._hand_action_server,
            'controllers': self._controllers,
            'joint_state': self._joint_state,
            'planning_scene_coke': self._planning_scene_coke,
        }


def _report(status, tracker):
    return json.dumps(
        {'status': status, **tracker.snapshot()},
        sort_keys=True,
    )


def _full_node_names(node):
    names = []
    for name, namespace in node.get_node_names_and_namespaces():
        prefix = namespace.rstrip('/')
        names.append(f'{prefix}/{name}' if prefix else f'/{name}')
    return names


def run_probe(*, timeout, poll_period, completion_gate=None):
    import rclpy
    from control_msgs.action import FollowJointTrajectory, GripperCommand
    from controller_manager_msgs.srv import ListControllers
    from moveit_msgs.srv import GetPlanningScene
    from rclpy.action import ActionClient
    from sensor_msgs.msg import JointState

    ros_log_dir = os.environ.get('ROS_LOG_DIR')
    if ros_log_dir:
        os.makedirs(ros_log_dir, exist_ok=True)
    tracker = ReadinessTracker()
    completion_started = completion_gate is None
    if completion_started:
        tracker.begin_completion_phase()
    rclpy.init()
    node = rclpy.create_node(
        'panda_e2e_readiness_probe',
        start_parameter_services=False,
        enable_rosout=False,
    )
    arm_action = ActionClient(
        node,
        FollowJointTrajectory,
        '/panda_arm_controller/follow_joint_trajectory',
    )
    hand_action = ActionClient(
        node,
        GripperCommand,
        '/panda_hand_controller/gripper_cmd',
    )
    controllers_client = node.create_client(
        ListControllers,
        '/controller_manager/list_controllers',
    )
    scene_client = node.create_client(GetPlanningScene, '/get_planning_scene')

    def observe_joint_state(message):
        tracker.observe_joint_names(message.name)

    joint_subscription = node.create_subscription(
        JointState,
        '/joint_states',
        observe_joint_state,
        10,
    )
    controllers_future = None
    scene_future = None
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if (
                not completion_started
                and os.path.exists(completion_gate)
            ):
                tracker.begin_completion_phase()
                completion_started = True
            tracker.observe_nodes(_full_node_names(node))
            tracker.observe_action_servers(
                arm=arm_action.server_is_ready(),
                hand=hand_action.server_is_ready(),
            )

            if controllers_future is not None and controllers_future.done():
                response = controllers_future.result()
                tracker.observe_controllers(
                    {controller.name: controller.state for controller in response.controller}
                )
                controllers_future = None
            if controllers_future is None and controllers_client.service_is_ready():
                controllers_future = controllers_client.call_async(
                    ListControllers.Request()
                )

            if scene_future is not None and scene_future.done():
                response = scene_future.result()
                tracker.observe_scene_objects(
                    collision_object.id
                    for collision_object in response.scene.world.collision_objects
                )
                scene_future = None
            if scene_future is None and scene_client.service_is_ready():
                request = GetPlanningScene.Request()
                request.components.components = 24
                scene_future = scene_client.call_async(request)

            for milestone in tracker.take_new_milestones():
                print(_report(milestone, tracker), flush=True)
                if milestone == 'ALL_READY':
                    return 0

            remaining = deadline - time.monotonic()
            if remaining > 0:
                rclpy.spin_once(node, timeout_sec=min(poll_period, remaining))

        print(_report('TIMEOUT', tracker), flush=True)
        return 1
    finally:
        # Keep the subscription referenced for the full probe lifetime.
        del joint_subscription
        node.destroy_node()
        rclpy.try_shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=float, default=300.0)
    parser.add_argument('--poll-period', type=float, default=0.1)
    parser.add_argument('--completion-gate')
    args = parser.parse_args()
    if args.timeout <= 0 or args.poll_period <= 0:
        parser.error('timeout and poll-period must be positive')
    return run_probe(
        timeout=args.timeout,
        poll_period=args.poll_period,
        completion_gate=args.completion_gate,
    )


if __name__ == '__main__':
    raise SystemExit(main())
