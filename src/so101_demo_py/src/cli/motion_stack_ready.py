"""Bounded readiness gate for controllers and MoveIt before scene setup."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True, slots=True)
class MotionStackReadiness:
    ready: bool
    phase: str
    failure_code: str | None
    evidence: dict[str, object]


CONTROLLER_NAMES = (
    "joint_state_broadcaster",
    "arm_controller",
    "gripper_controller",
)
MOVEIT_SERVICE_NAMES = (
    "/apply_planning_scene",
    "/get_planning_scene",
    "/plan_kinematic_path",
)
MOVEIT_ACTION_NAMES = (
    "/execute_trajectory",
    "/arm_controller/follow_joint_trajectory",
    "/gripper_controller/follow_joint_trajectory",
)
CONTROLLER_MANAGER_SERVICE = "/controller_manager/list_controllers"
# Minimum spacing between the starts of NEW ListControllers requests. spin_once returns at once
# whenever any callback is ready, so an unpaced loop floods controller_manager and starves the
# spawners' own list_controllers calls.
CONTROLLER_QUERY_MIN_INTERVAL_S = 0.1

_CONTROLLERS = CONTROLLER_NAMES
_SERVICES = MOVEIT_SERVICE_NAMES
_ACTIONS = MOVEIT_ACTION_NAMES


def controller_query_allowed(*, controller_service_visible: bool) -> bool:
    """Query controllers as soon as their own service is visible.

    Controller traffic deliberately does not wait for the aggregate MoveIt service/action
    graph. Gating it behind MoveIt made two different failures indistinguishable: a station
    stuck in hardware bring-up and a station whose MoveIt layer never appeared both ended as
    the same downstream readiness timeout.
    """

    return bool(controller_service_visible)


def poll_controller_states(
    client,
    pending,
    *,
    request_factory,
    spin_until_future_complete,
    node,
    timeout_s: float,
    query_evidence=None,
):
    """Advance one controller query without creating overlapping requests."""

    if pending is None:
        if not client.service_is_ready():
            return None, None
        pending = client.call_async(request_factory())
        if query_evidence is not None:
            query_evidence['requests_started']+=1
    spin_until_future_complete(node, pending, timeout_sec=timeout_s)
    if not pending.done():
        return pending, None
    response = pending.result()
    if query_evidence is not None:
        query_evidence['responses_completed']+=1
        query_evidence['last_response_monotonic_ns']=time.monotonic_ns()
        query_evidence['last_response_was_none']=response is None
    if response is None:
        return None, None
    return None, {value.name: value.state for value in response.controller}


def evaluate_readiness(
    *,
    controllers: dict[str, str],
    services: dict[str, bool],
    actions: dict[str, bool],
    controller_service_visible: bool = True,
    controller_call_timed_out: bool = False,
    require_neck: bool = False,
) -> MotionStackReadiness:
    """Aggregate the final readiness verdict from independent observations.

    The controller axis is evaluated first so that its two distinct failures stay
    distinguishable: the direct service never became visible (DDS/registration boundary) or
    it was visible but the bounded call never returned (call boundary).
    """

    if not controller_service_visible:
        return MotionStackReadiness(
            False,
            "CONTROLLERS",
            "MOTION_STACK_CONTROLLER_SERVICE_INVISIBLE",
            {"dependency": CONTROLLER_MANAGER_SERVICE},
        )
    if controller_call_timed_out and not controllers:
        return MotionStackReadiness(
            False,
            "CONTROLLERS",
            "MOTION_STACK_CONTROLLER_CALL_TIMEOUT",
            {"dependency": CONTROLLER_MANAGER_SERVICE},
        )
    required_controllers=(*_CONTROLLERS,'neck_controller') if require_neck else _CONTROLLERS
    for name in required_controllers:
        if controllers.get(name) != "active":
            return MotionStackReadiness(
                False,
                "CONTROLLERS",
                "MOTION_STACK_CONTROLLER_NOT_ACTIVE",
                {"dependency": name, "observed": controllers.get(name)},
            )
    for name in _SERVICES:
        if not services.get(name, False):
            return MotionStackReadiness(
                False,
                "MOVEIT_SERVICES",
                "MOTION_STACK_MOVEIT_SERVICE_UNAVAILABLE",
                {"dependency": name},
            )
    required_actions=(*_ACTIONS,'/neck_controller/follow_joint_trajectory') if require_neck else _ACTIONS
    for name in required_actions:
        if not actions.get(name, False):
            return MotionStackReadiness(
                False,
                "ACTIONS",
                "MOTION_STACK_ACTION_UNAVAILABLE",
                {"dependency": name},
            )
    return MotionStackReadiness(
        True,
        "READY",
        None,
        {
            "controllers": controllers,
            "services": services,
            "actions": actions,
        },
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="motion_stack_ready")
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--include-neck", action="store_true")
    options = parser.parse_args(arguments)
    if options.timeout_s <= 0.0:
        parser.error("--timeout-s must be positive")

    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from controller_manager_msgs.srv import ListControllers
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
    from rclpy.action import ActionClient

    rclpy.init()
    node = rclpy.create_node("so101_motion_stack_readiness")
    controller_client = node.create_client(
        ListControllers, "/controller_manager/list_controllers"
    )
    service_clients = {
        "/apply_planning_scene": node.create_client(
            ApplyPlanningScene, "/apply_planning_scene"
        ),
        "/get_planning_scene": node.create_client(
            GetPlanningScene, "/get_planning_scene"
        ),
        "/plan_kinematic_path": node.create_client(
            GetMotionPlan, "/plan_kinematic_path"
        ),
    }
    action_clients = {
        "/execute_trajectory": ActionClient(
            node, ExecuteTrajectory, "/execute_trajectory"
        ),
        "/arm_controller/follow_joint_trajectory": ActionClient(
            node,
            FollowJointTrajectory,
            "/arm_controller/follow_joint_trajectory",
        ),
        "/gripper_controller/follow_joint_trajectory": ActionClient(
            node,
            FollowJointTrajectory,
            "/gripper_controller/follow_joint_trajectory",
        ),
    }
    if options.include_neck:
        action_clients['/neck_controller/follow_joint_trajectory']=ActionClient(
            node,FollowJointTrajectory,'/neck_controller/follow_joint_trajectory')
    deadline = time.monotonic() + options.timeout_s
    latest = MotionStackReadiness(
        False, "CONTROLLERS", "MOTION_STACK_CONTROLLER_NOT_ACTIVE", {}
    )
    try:
        controllers: dict[str, str] = {}
        controller_future = None
        controller_query_deadline = None
        controller_call_expired = False
        controller_service_seen = False
        controller_query_last_start = None
        query_evidence={'requests_started':0,'responses_completed':0,
                        'last_response_monotonic_ns':None,'last_response_was_none':None,
                        'query_timeouts':0,'last_completed_controllers':{}}
        def original_query_result(result):
            return replace(result,evidence={**result.evidence,'controller_query':{
                **query_evidence,'controllers':dict(controllers),
                'service_visible':controller_client.service_is_ready(),
                'service_seen':controller_service_seen,'pending':controller_future is not None}})
        while rclpy.ok() and time.monotonic() < deadline:
            services = {
                name: client.service_is_ready()
                for name, client in service_clients.items()
            }
            actions = {
                name: client.server_is_ready()
                for name, client in action_clients.items()
            }
            controller_service_visible = controller_client.service_is_ready()
            controller_service_seen = (
                controller_service_seen or controller_service_visible
            )
            if controller_query_allowed(
                controller_service_visible=controller_service_visible
            ) and (
                controller_future is not None
                or controller_query_last_start is None
                or time.monotonic() - controller_query_last_start
                >= CONTROLLER_QUERY_MIN_INTERVAL_S
            ):
                remaining = max(0.0, deadline - time.monotonic())
                if controller_future is None:
                    controller_query_deadline = min(deadline, time.monotonic() + 1.0)
                    started_before = query_evidence['requests_started']
                    query_start_time = time.monotonic()
                else:
                    started_before = None
                controller_future, observed = poll_controller_states(
                    controller_client,
                    controller_future,
                    request_factory=ListControllers.Request,
                    spin_until_future_complete=rclpy.spin_until_future_complete,
                    node=node,
                    timeout_s=min(remaining, max(0.0, controller_query_deadline - time.monotonic())),
                    query_evidence=query_evidence,
                )
                if (
                    started_before is not None
                    and query_evidence['requests_started'] > started_before
                ):
                    controller_query_last_start = query_start_time
                if observed is not None:
                    controllers = observed
                    query_evidence['last_completed_controllers'] = dict(observed)
                    controller_call_expired = False
                if controller_future is not None and time.monotonic() >= controller_query_deadline:
                    # Retire only this read-only query's client bookkeeping. A later response
                    # cannot become a readiness observation; the whole gate deadline is fixed.
                    controller_client.remove_pending_request(controller_future)
                    controller_future = None
                    controllers = {}
                    query_evidence['query_timeouts'] += 1
                    controller_call_expired = True
            latest = evaluate_readiness(
                controllers=controllers,
                services=services,
                actions=actions,
                controller_service_visible=controller_service_seen,
                require_neck=options.include_neck,
            )
            if latest.ready:
                print(json.dumps(asdict(original_query_result(latest)), sort_keys=True), flush=True)
                return 0
            rclpy.spin_once(node, timeout_sec=0.05)
        latest = evaluate_readiness(
            controllers=controllers,
            services={
                name: client.service_is_ready()
                for name, client in service_clients.items()
            },
            actions={
                name: client.server_is_ready()
                for name, client in action_clients.items()
            },
            controller_service_visible=controller_service_seen,
            controller_call_timed_out=controller_future is not None or controller_call_expired,
            require_neck=options.include_neck,
        )
        print(json.dumps(asdict(original_query_result(latest)), sort_keys=True), flush=True)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()
