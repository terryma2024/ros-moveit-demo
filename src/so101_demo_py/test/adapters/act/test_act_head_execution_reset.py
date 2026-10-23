"""Head reset uses advancing authoritative full-state proof before admission."""

from types import SimpleNamespace
import time

import mujoco
import pytest

from test_act_head_execution_scene import scene_inputs, register_safety


class Node:
    def __init__(self): self.callbacks = []; self.retired = []
    def create_subscription(self, kind, topic, callback, qos):
        self.callbacks.append(callback)
        return callback
    def destroy_subscription(self, subscription): self.retired.append(subscription); return True


def setup_scene(tmp_path, *, damage=None):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    from so101_demo.adapters.act.head_execution_reset import OwnedHeadScene
    inputs, policy, document = scene_inputs(tmp_path)
    register_safety(inputs, document)
    safety = load_scene_safety(inputs)
    inputs.document['development_pose'] = dict(arm_rad=[-.25,0.,.6,.8,0.,.8],
                                              neck_rad=.1,cup_xyz=[.02,-.28,.165])
    node, events = Node(), []
    data = mujoco.MjData(safety.checker.model)
    state = dict(session=inputs.run['session_id'], epoch=2, step=5, paused=False)

    def publish():
        from so101_mujoco_support.msg import SceneStateEvidence
        message = SceneStateEvidence()
        message.simulation_session_id = state['session']
        message.reset_epoch, message.simulation_step, message.paused = state['epoch'], state['step'], state['paused']
        message.header.stamp.sec = 0 if state['step'] == 0 else 1
        message.model_sha256 = safety.checker.model_sha256
        message.qpos, message.qvel = data.qpos.tolist(), data.qvel.tolist()
        now = time.monotonic_ns()
        message.clock_interval_begin_monotonic_ns = now-1000
        message.clock_interval_end_monotonic_ns = now
        for callback in node.callbacks: callback(message)

    class Services:
        def pause(self, paused, **kw):
            events.append(('pause',paused)); state['paused'] = paused; publish(); return True
        def switch(self, *, activate, deactivate, **kw):
            events.append(('switch',tuple(activate),tuple(deactivate))); return True
        def active(self, names, **kw): return True
        def reset_pose(self, pose, **kw):
            events.append(('reset',pose))
            mujoco.mj_resetData(safety.checker.model,data)
            for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                                   (*pose['arm_rad'],pose['neck_rad']),strict=True):
                data.qpos[safety.joint_map[name]['qpos']] = value
            q = safety.free_body_map['plastic_cup']['qpos']
            data.qpos[q:q+7] = (*pose['cup_xyz'],1.,0.,0.,0.)
            if damage == 'pose': data.qpos[q] += .02
            elif damage == 'velocity': data.qvel[0] = .1
            state['epoch'] += 0 if damage == 'epoch' else 1
            if damage == 'session': state['session'] = 'foreign'
            state['step'] = 0 if damage != 'step' else 2
            publish(); return True
        def close(self): return {'closed':True}

    scene = OwnedHeadScene(node=node, inputs=inputs, safety=safety, max_age_s=.25,
        services=Services(), emit=lambda kind,record: events.append((kind,record)))
    publish()
    return scene, inputs, safety, node, events


def test_reset_uses_fresh_next_epoch_step_zero_and_exact_declared_pose(tmp_path):
    scene, inputs, safety, node, events = setup_scene(tmp_path)
    try:
        receipt = scene.reset(timeout_s=.1)
        assert receipt['old_epoch'] == 2 and receipt['reset_epoch'] == 3
        assert receipt['paused'] is True and receipt['simulation_step'] == 0
        assert scene.observer.snapshot()['reset_epoch'] == 3
        resets = [r for r in events if r[0] == 'reset']
        assert resets == [('reset',inputs.document['development_pose'])]
        assert ('switch',(),('arm_controller','gripper_controller')) in events
        assert ('switch',('arm_controller','gripper_controller'),()) in events
        assert not any('neck_controller' in row[1] or 'neck_controller' in row[2]
                       for row in events if row[0] == 'switch'), 'the neck is activated by its owner only'
        with pytest.raises(PermissionError, match='REUSED'): scene.reset(timeout_s=.1)
    finally: assert scene.close()['closed'] is True
    assert len(node.retired) == 1


def test_the_neck_owner_activates_the_neck_after_the_other_controllers_and_before_the_final_pause(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    scene.neck_activation = lambda *, deadline: events.append(('neck_activate',))
    try:
        scene.reset(timeout_s=.1)
        names = [row[0] if row[0] != 'switch' else ('switch', bool(row[1])) for row in events
                 if row[0] in ('switch', 'neck_activate', 'pause')]
        activate = names.index(('switch', True))
        assert names[activate + 1] == 'neck_activate'
        assert names.index('neck_activate') < len(names) - 1 - names[::-1].index('pause')
    finally: scene.close()


def test_reset_refuses_a_neck_that_is_still_active(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    scene.services.neck_state = lambda *, deadline: 'active'
    try:
        with pytest.raises(PermissionError, match='HEAD_RESET_NECK_ACTIVE'):
            scene.reset(timeout_s=.1)
        assert not any(row[0] in ('switch', 'reset') for row in events)
    finally: scene.close()


def test_a_failing_neck_activation_fails_the_reset_without_a_receipt(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    def refuse(*, deadline):
        raise PermissionError('HEAD_NECK_ACTIVATION_REFUSED')
    scene.neck_activation = refuse
    try:
        with pytest.raises(PermissionError, match='HEAD_NECK_ACTIVATION_REFUSED'):
            scene.reset(timeout_s=.1)
        assert scene.receipt is None
        assert [r for r in events if r[0] == 'pause'][-1] == ('pause', True)
    finally: scene.close()


def test_reset_waits_for_startup_controllers_before_first_pause(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    checks = []
    def ready(names, **kwargs):
        checks.append(tuple(names))
        assert not any(row[0] == 'pause' for row in events) or len(checks) > 2
        return len(checks) >= 2
    scene.services.active = ready
    try:
        scene.reset(timeout_s=.1)
        assert len(checks) >= 3
    finally: scene.close()


@pytest.mark.parametrize('damage',['pose','velocity','epoch','session','step'])
def test_reset_bad_authoritative_proof_leaves_world_paused(tmp_path,damage):
    scene, _, _, node, events = setup_scene(tmp_path,damage=damage)
    try:
        with pytest.raises((ValueError,PermissionError,TimeoutError)):
            scene.reset(timeout_s=.02)
        assert [r for r in events if r[0] == 'pause'][-1] == ('pause',True)
        assert not any(r[0] == 'switch' and r[1] for r in events)
    finally: scene.close()


def test_scene_failed_subscription_retirement_cannot_become_success(tmp_path,monkeypatch):
    scene, _, _, node, _ = setup_scene(tmp_path)
    monkeypatch.setattr(node,'destroy_subscription',lambda subscription:False)
    first=scene.close()
    assert first['closed'] is False
    assert scene.close() == first


def test_reset_waits_for_owned_spawners_within_same_deadline_before_pause(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    deadlines = []
    def startup_ready(*, deadline):
        deadlines.append(deadline)
        assert not events
        return {'ready': True}
    events.clear()
    scene.startup_ready = startup_ready
    started = time.monotonic()
    try:
        scene.reset(timeout_s=.1)
        assert len(deadlines) == 1
        assert started < deadlines[0] <= started+.101
    finally:
        scene.close()


def test_failed_owned_spawner_refuses_reset_before_any_pose_change(tmp_path):
    scene, _, _, _, events = setup_scene(tmp_path)
    def startup_ready(*, deadline):
        raise PermissionError('HEAD_STACK_SPAWNER_FAILED')
    scene.startup_ready = startup_ready
    events.clear()
    try:
        with pytest.raises(PermissionError, match='HEAD_STACK_SPAWNER_FAILED'):
            scene.reset(timeout_s=.1)
        assert not any(row[0] in ('switch', 'reset') for row in events)
    finally:
        scene.close()
