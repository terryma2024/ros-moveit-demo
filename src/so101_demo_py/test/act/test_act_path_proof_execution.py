"""A proven path must never enter the legacy absolute-goal branch."""

import pytest

from so101_demo.act.execution import ActExecutionAdapter

from test_act_execution import Clock, Port
from test_act_path_proof_permits import proof_authority
from test_act_physics import scene


def test_proof_without_commit_ports_cannot_send_fake_goals(scene):
    authority, prefix, _, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    arm, gripper = Port(), Port()
    adapter = ActExecutionAdapter(
        arm, gripper, permit_port=authority,
        sim_clock=lambda: 1., monotonic=lambda: 10.,
        progress=lambda: None, submit_lead_s=.03,
        accept_timeout_s=.02, stop_timeout_s=.03,
        reference_port=lambda _: prefix['positions'][0],
    )
    adapter.begin_attempt('s', 'a')
    with pytest.raises(PermissionError, match='PROOF_COMMIT_PORT_REQUIRED'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == []
    assert checks == [1]


def proof_adapter(scene, *, arm=None, gripper=None):
    authority, prefix, current, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    clock = Clock()
    clock.sim, clock.wall = 4.85, 10.06
    authority.monotonic = lambda: clock.wall
    physical = current['snapshot']
    physical['sim_time_s'] = 4.85
    physical['controller_bridge']['time_s'] = 4.85
    physical['controller_start_time_s'] = 5.
    current['dual_clock'] = dict(wall_s=10.05, sim_s=4.85,
                                 error_s=.001, continuous=True)
    current['controller_stop_confirmed'] = True
    arm, gripper = arm or Port(), gripper or Port()
    goal_checks = []

    def goal_boundary(goals, proof, readback):
        goal_checks.append((goals, proof, readback))
        return True

    adapter = ActExecutionAdapter(
        arm, gripper, permit_port=authority,
        sim_clock=lambda: clock.sim, monotonic=lambda: clock.wall,
        progress=clock.progress, submit_lead_s=.15,
        accept_timeout_s=.08, stop_timeout_s=.03,
        reference_port=lambda _: prefix['positions'][0],
        proof_reference_port=lambda start: dict(
            requested_sim_time_s=start,
            positions=physical['controller_start_positions'],
            velocities=physical['controller_start_velocities']),
        proof_clock_port=lambda: dict(wall_s=clock.wall, sim_s=clock.sim,
                                      error_s=.001, continuous=True),
        proof_goal_port=goal_boundary,
        proof_timing=dict(max_prefix_age_s=.2, max_state_age_s=.1,
                          observation_jitter_s=.01, start_jitter_s=.02,
                          first_target_jitter_s=.02),
    )
    adapter.begin_attempt('s', 'a')
    return adapter, authority, prefix, permit, current, clock, arm, gripper, checks, goal_checks


def test_proof_goals_use_relative_grid_and_one_checker_call(scene):
    from so101_demo.adapters.act.ros_execution import trajectory_message

    (adapter, authority, prefix, permit, _, _, arm, gripper,
     checks, goal_checks) = proof_adapter(scene)
    assert adapter.submit(prefix, permit) == '1:1'
    left, right = arm.goals[0], gripper.goals[0]
    assert left['header_stamp_s'] == right['header_stamp_s'] == 5.
    assert left['time_from_start_s'][:3] == (0., .052, .054)
    assert left['positions'][0] + right['positions'][0] == prefix['positions'][0]
    assert len(left['positions']) == len(right['positions']) == 601
    for goal in (left, right):
        message = trajectory_message(goal)
        assert (message.header.stamp.sec,
                message.header.stamp.nanosec) == (5, 0)
        assert len(message.points) == 601
        assert [(point.time_from_start.sec,
                 point.time_from_start.nanosec)
                for point in (message.points[0], message.points[1],
                              message.points[-1])] == [
                                  (0, 0), (0, 52000000), (1, 250000000)]
    assert len(goal_checks) == 1 and checks == [1]


def test_goal_boundary_cannot_mutate_goals_after_exact_check(scene):
    (adapter, _, prefix, permit, _, _, arm, gripper,
     checks, _) = proof_adapter(scene)

    def corrupt(goals, _proof, _readback):
        goals[0]['positions'] = goals[0]['positions'][:-1] + ((.001,) * 5,)
        return True

    adapter.proof_goal_port = corrupt
    with pytest.raises(ValueError, match='PATH_GOALS_MISMATCH'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == []
    assert checks == [1]


def test_changed_physical_state_or_reference_denies_before_fake_send(scene):
    (adapter, _, prefix, permit, current, _, arm, gripper,
     checks, _) = proof_adapter(scene)

    def drift(_goals, _proof, _readback):
        current['snapshot']['model_qvel'] = (0.001,) + tuple(
            current['snapshot']['model_qvel'][1:])
        return True

    adapter.proof_goal_port = drift
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == [] and checks == [1]

    (adapter, _, prefix, permit, _, _, arm, gripper,
     checks, _) = proof_adapter(scene)
    adapter.proof_reference_port = lambda start: dict(
        requested_sim_time_s=start, positions=(.001,) * 6,
        velocities=(0.,) * 6)
    with pytest.raises(PermissionError, match='PROOF_REFERENCE_CHANGED'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == [] and checks == [1]


def test_lost_stop_or_clock_proof_denies_before_fake_send(scene):
    (adapter, _, prefix, permit, current, _, arm, gripper,
     checks, _) = proof_adapter(scene)

    def lose_stop(_goals, _proof, _readback):
        current['controller_stop_confirmed'] = False
        return True

    adapter.proof_goal_port = lose_stop
    with pytest.raises(PermissionError, match='PROOF_STOP_UNCONFIRMED'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == [] and checks == [1]

    (adapter, _, prefix, permit, _, _, arm, gripper,
     checks, _) = proof_adapter(scene)
    adapter.proof_clock_port = lambda: dict(
        wall_s=10.06, sim_s=4.85, error_s=.001,
        continuous=False)
    with pytest.raises(ValueError, match='PROOF_CLOCK_INVALID'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == [] and checks == [1]

def test_proof_acceptance_at_common_start_cancels_both_fake_goals(scene):
    holder = {}

    class DelayedPort(Port):
        def accepted(self, goal_id):
            return True if holder['clock'].sim >= 5. else None

    (adapter, _, prefix, permit, _, clock, arm, gripper,
     checks, _) = proof_adapter(scene, gripper=DelayedPort())
    holder['clock'] = clock
    clock.progress = lambda: (
        setattr(clock, 'sim', clock.sim + .03),
        setattr(clock, 'wall', clock.wall + .001))
    adapter.progress = clock.progress
    with pytest.raises(RuntimeError, match='CONTROLLER_PAIR_FAILED'):
        adapter.submit(prefix, permit)
    assert arm.cancels == gripper.cancels == ['1']
    assert adapter.state == 'STOPPED' and checks == [1]


def test_partial_proof_acceptance_cancels_both_fake_goals(scene):
    (adapter, _, prefix, permit, _, _, arm, gripper,
     checks, _) = proof_adapter(scene, gripper=Port(False))
    with pytest.raises(RuntimeError, match='CONTROLLER_PAIR_FAILED'):
        adapter.submit(prefix, permit)
    assert arm.cancels == gripper.cancels == ['1']
    assert adapter.state == 'STOPPED' and checks == [1]


def test_state_drift_after_first_fake_send_never_sends_second(scene):
    holder = {}

    class DriftingArm(Port):
        def send(self, goal):
            goal_id = super().send(goal)
            physical = holder['current']['snapshot']
            physical['model_qvel'] = (0.001,) + tuple(
                physical['model_qvel'][1:])
            return goal_id

    (adapter, _, prefix, permit, current, _, arm, gripper,
     checks, _) = proof_adapter(scene, arm=DriftingArm())
    holder['current'] = current
    with pytest.raises(RuntimeError, match='CONTROLLER_PAIR_FAILED'):
        adapter.submit(prefix, permit)
    assert len(arm.goals) == 1 and arm.cancels == ['1']
    assert gripper.goals == [] and checks == [1]
