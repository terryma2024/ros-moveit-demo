"""The chained planning control and the dynamic plan prefix adapter."""

from __future__ import annotations

from dataclasses import replace
import time
from typing import Any, Callable

from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
from so101_demo.runtime.parallel_worker_parts.receipts import (
    PlanPrefixReceipt,
    PlanSegmentReceipt,
)


class _ChainedPlanningControl:
    def __init__(self, control: Any) -> None:
        self._control = control
        self._start_state = None

    def plan_tcp_motion(self, request: Any):
        if self._start_state is not None:
            request = replace(request, start_state=self._start_state)
        plan = self._control.plan_tcp_motion(request)
        if getattr(plan, "accepted", None) is True:
            terminal = getattr(plan, "terminal_state", None)
            if terminal is None:
                raise RuntimeError("CUP_POSE_PLAN_TERMINAL_STATE_MISSING")
            self._start_state = terminal
        return plan


class RosDynamicPlanPrefixAdapter:
    """Use ``RosDynamicPlanner`` for every dynamic plan-only motion state."""

    def __init__(
        self,
        node: Any,
        template: Any,
        scene: Any,
        *,
        planner_factory: Callable[[Any, tuple[str, ...]], Any] | None = None,
        target_resolver: Callable[[Any, Any], Any] | None = None,
        plan_state: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        owned_context: Any | None = None,
    ) -> None:
        if planner_factory is None:
            from so101_demo.ros.dynamic_planner import RosDynamicPlanner

            planner_factory = RosDynamicPlanner
        if target_resolver is None:
            from so101_demo.core.dynamic_pick import resolve_motion_targets

            target_resolver = resolve_motion_targets
        if plan_state is None:
            from so101_demo.application.dynamic_plan_only import plan_dynamic_state_with_scene_gates

            plan_state = plan_dynamic_state_with_scene_gates
        from so101_demo.application.dynamic_plan_only import DynamicPlanningOptions

        self._template = template
        self._scene = scene
        self._planner = planner_factory(node, template.arm_joint_names)
        self._target_resolver = target_resolver
        self._plan_state = plan_state
        self._clock = clock
        self._owned_node = node if owned_context is not None else None
        self._owned_context = owned_context
        self._closed = False
        self._options = DynamicPlanningOptions(
            template.planning_frame,
            template.planning_group,
            template.tcp_link,
            template.position_tolerance_m,
            template.orientation_tolerance_rad,
            template.planning_timeout_s,
            template.velocity_scaling,
            template.acceleration_scaling,
        )

    def __call__(self, lease: Any, admitted: Any, states: tuple[State, ...]):
        del lease
        if states != DYNAMIC_REACHABILITY_STATES:
            raise RuntimeError("PLAN_PREFIX_STATES_NOT_AUTHORITATIVE")
        targets = self._target_resolver(admitted, self._template)
        control = _ChainedPlanningControl(self._planner.control)
        segments = []
        for state in states:
            plan, before, after = self._plan_state(
                state=state,
                provider=targets,
                control=control,
                options=self._options,
                scene=self._scene,
                sample=admitted,
                template=self._template,
            )
            if getattr(plan, "accepted", None) is not True:
                raise RuntimeError("CUP_POSE_PLAN_FAILED")
            terminal = getattr(plan, "terminal_state", None)
            if terminal is None:
                raise RuntimeError("CUP_POSE_PLAN_TERMINAL_STATE_MISSING")
            segments.append(
                PlanSegmentReceipt(
                    state,
                    getattr(plan, "start_state", None),
                    terminal,
                    plan,
                    before,
                    after,
                )
            )
        return PlanPrefixReceipt(tuple(segments), self._clock())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._planner.close()
        finally:
            try:
                if self._owned_node is not None:
                    self._owned_node.destroy_node()
            finally:
                if self._owned_context is not None:
                    self._owned_context.shutdown()
