"""The independent physics checker owns no ROS clients and fails closed on IPC loss."""
import os,time
from pathlib import Path
import pytest
from so101_demo.adapters.act.physics import MujocoPathProcess
from test_act_physics import scene,checker,inputs


def config(scene):
    return dict(model_path=str(scene),protected_roots=('base',),cup_joint='cup_free_joint',gripper_body='gripper',
        path_step_s=.002,path_clearance_m=.002,velocity_limit_rad_s=(100.,)*6,
        acceleration_limit_rad_s2=(1e6,)*6,allowed_pairs_by_phase={})


def test_separate_process_reconstructs_identical_bridge_and_held_cup_contacts(scene):
    inline=checker(scene);port=MujocoPathProcess(check_timeout_s=.2,start_timeout_s=2.,**config(scene))
    try:
        assert port.worker_pid!=os.getpid() and port.model_sha256==inline.model_sha256
        for holding in (False,True):
            p,s=inputs(inline,holding=holding)
            assert port.check_path(p,s)==inline.check_path(p,s)
            assert port.last_check==inline.last_check
        p,s=inputs(inline);p['positions']=(s['controller_start_positions'],)
        assert inline.check_path(p,s) and port.check_path(p,s)
    finally:port.close()
    assert not port.process.is_alive()
    assert not port.check_path(p,s) and port.last_check['reason']=='PATH_WORKER_UNAVAILABLE'


def stalled_worker(connection,configuration):
    from so101_demo.adapters.act.physics import MujocoPathChecker
    m=MujocoPathChecker(**configuration)
    connection.send(dict(pid=os.getpid(),model_sha256=m.model_sha256))
    connection.recv();time.sleep(2)


def test_stalled_worker_cannot_extend_path_deadline_or_leave_a_child(scene,monkeypatch):
    import so101_demo.adapters.act.physics as module
    monkeypatch.setattr(module,'_path_worker',stalled_worker)
    inline=checker(scene);p,s=inputs(inline)
    port=MujocoPathProcess(check_timeout_s=.01,start_timeout_s=2.,**config(scene))
    try:
        assert not port.check_path(p,s)
        assert port.last_check['reason']=='PATH_CHECK_TIMEOUT'
        assert not port.process.is_alive()
        assert not port.check_path(p,s) and port.last_check['reason']=='PATH_WORKER_UNAVAILABLE'
    finally:port.close()


def forged_model_worker(connection,configuration):
    connection.send(dict(pid=os.getpid(),model_sha256='0'*64))
    connection.recv()


def test_changed_compiled_model_cannot_enter_service_or_leave_owned_child(scene,monkeypatch):
    import multiprocessing
    import so101_demo.adapters.act.physics as module
    before={p.pid for p in multiprocessing.active_children()}
    monkeypatch.setattr(module,'_path_worker',forged_model_worker)
    with pytest.raises(ValueError,match='PATH_WORKER_MODEL_INVALID'):
        MujocoPathProcess(check_timeout_s=.2,start_timeout_s=2.,**config(scene))
    assert {p.pid for p in multiprocessing.active_children()}==before


def test_owned_worker_death_cannot_fall_back_to_inline_physics(scene):
    inline=checker(scene);p,s=inputs(inline)
    port=MujocoPathProcess(check_timeout_s=.2,start_timeout_s=2.,**config(scene))
    try:
        port.process.terminate();port.process.join(timeout=1.)
        assert not port.check_path(p,s)
        assert port.last_check['reason']=='PATH_WORKER_UNAVAILABLE'
    finally:port.close()
