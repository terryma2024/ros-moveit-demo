"""Exercise the provider's launcher path without starting simulation or motion."""

import json
import threading
from types import SimpleNamespace

import pytest

from test_act_head_execution_composition import build_inputs, module


@pytest.mark.parametrize('fail_start', [False, True])
@pytest.mark.parametrize('legacy_binding', [False, True])
def test_launcher_services_callbacks_on_its_new_local_node(monkeypatch, tmp_path, fail_start, legacy_binding):
    """Omitting the newly built node from the executor leaves this callback silent."""
    from rclpy.clock import Clock, ClockType
    from so101_demo.adapters.act import head_execution_provider as provider
    from so101_demo.adapters.act import head_stopped_capture, ros_neck

    inputs, _ = build_inputs(tmp_path)
    values = dict(submit_lead_s=.01, stop_latency_s=1., stop_velocity_rad_s=.01,
                  max_age_s=.15, search_timeout_s=30.)
    config = tmp_path / 'development.json'
    config.write_text(json.dumps({'values': values, 'camera': {'frame_id': 'head_camera_frame'}}))
    inputs.refs['development_config']['path'] = str(config)
    if legacy_binding:
        inputs.refs['binding'] = {'path': str(config)}
    else:
        inputs.refs.pop('binding',None)
    delivered = threading.Event()
    nodes = []
    timers = []

    def capture(node, port, **kwargs):
        assert kwargs['frame_id'] == 'head_camera_frame'
        assert port.stop_velocity == values['stop_velocity_rad_s']
        assert port.max_age == values['max_age_s']
        nodes.append(node)
        timers.append(node.create_timer(.01, delivered.set,
                                       clock=Clock(clock_type=ClockType.STEADY_TIME)))
        return SimpleNamespace()

    # The external stack and camera are outside this executor boundary. The node,
    # context, controller port, executor and callback are genuine rclpy resources.
    monkeypatch.setattr(head_stopped_capture, 'StoppedHeadCapture', capture)
    def neck(*args, **kwargs):
        assert kwargs['command_guard'](0., .1) is False
        return SimpleNamespace()
    monkeypatch.setattr(ros_neck, 'RosNeckSearchPort', neck)

    class Launcher:
        evidence = {'stack': {'nodes': ['controller_manager']}}

        def start(self):
            if fail_start:
                raise RuntimeError('controlled stack startup failure')

        def identity_snapshot(self, role):
            raise AssertionError('identity must be read after guarded ARM, never during assembly')

    entries = {name: {'callable': lambda **k: None, 'keywords': {}}
               for name in ('detector', 'owner')}
    entries['stack'] = {'callable': Launcher, 'keywords': {}}
    composition = module().HeadExecutionComposition.open(inputs)

    def runner(comp, handle, **kwargs):
        assert 'controller_identity' not in handle
        assert handle['node'] is nodes[0] and handle['node'] is not None
        assert delivered.wait(1.), 'launcher node callbacks were never serviced'
        from geometry_msgs.msg import TransformStamped
        from rclpy.time import Time
        transform = TransformStamped()
        transform.header.frame_id = 'base'
        transform.child_frame_id = 'head_camera_frame'
        transform.header.stamp.sec = 1
        transform.transform.rotation.w = 1.
        transform.transform.translation.x = .1
        handle['buffer'].set_transform(transform, 'controlled-tf-input')
        observed = handle['buffer'].lookup_transform('base', 'head_camera_frame', Time(seconds=1.))
        assert observed.header.stamp == transform.header.stamp
        assert observed.transform.translation.x == .1
        assert handle['local_ros'].listener.node is nodes[0]
        assert handle['settlement'].__module__ == 'so101_demo.act.head_feedback'
        return 0

    plan = {'constructors': entries, 'runner': {'callable': runner}}
    try:
        if fail_start:
            with pytest.raises(provider.HeadExecutionProviderRefused,
                               match='controlled stack startup failure'):
                provider.provide(composition, inputs, plan=plan)
            assert not nodes[0].context.ok(), 'failed assembly leaked its private ROS context'
            return
        assert provider.provide(composition, inputs, plan=plan) == 0
        assert not nodes[0].context.ok(), 'provider returned with a live ROS context'
        assert not any(thread.name.startswith('head-local-spin-')
                       for thread in threading.enumerate())
    finally:
        for node in nodes:
            for timer in timers:
                node.destroy_timer(timer)
            context = node.context
            if context.ok():
                context.shutdown()
            for thread in threading.enumerate():
                if thread.name.startswith('head-local-spin-'):
                    thread.join(timeout=1.)
            node.destroy_node()
        composition.writer.finish({'execution': 'FAILED', 'reason': 'test cleanup'})
