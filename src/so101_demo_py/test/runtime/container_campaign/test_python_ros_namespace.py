"""Addressing gates for private container Python contexts; no motion or hardware."""

import importlib

import pytest


def module():
    return importlib.import_module('so101_demo.runtime.container_campaign.ros_namespace')


def test_unmarked_generic_and_macos_processes_keep_original_init_arguments():
    assert module().container_ros_init_options(environment={})=={}
    assert module().container_ros_init_options(environment={'ROS_NAMESPACE':'/generic'})=={}


@pytest.mark.parametrize('problem',['root','relative','mismatch'])
def test_invalid_or_conflicting_container_namespace_refuses_before_context_init(problem):
    namespace={'root':'/','relative':'act/worker','mismatch':'/act/campaign/w00'}[problem]
    environment=dict(SO101_ACT_CONTAINER_NAMESPACE=namespace,
        ROS_NAMESPACE='/foreign' if problem=='mismatch' else namespace)
    with pytest.raises(ValueError):module().container_ros_init_options(environment=environment)


def test_actual_jazzy_context_resolves_python_endpoints_in_private_namespace():
    import rclpy
    namespace='/act/context_test/w00'
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=namespace,ROS_NAMESPACE=namespace))
    context=rclpy.context.Context()
    context.init(**options,domain_id=231)
    node=None
    try:
        node=rclpy.create_node('scope_probe',context=context)
        assert node.get_namespace()==namespace
        assert node.resolve_topic_name('/cup_pose')==namespace+'/cup_pose'
        assert node.resolve_service_name('/mujoco_ros2_control_node/set_pause')==namespace+'/mujoco_ros2_control_node/set_pause'
        assert node.resolve_topic_name('/tf')==namespace+'/tf'
        assert node.resolve_topic_name('/task_camera/color')==namespace+'/task_camera/color'
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


def test_current_worker_inventory_accepts_only_its_own_complete_scoped_graph():
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    namespace='/act/campaign/w00'
    base=tuple(sorted(RuntimeBinding.expected_worker_nodes()+('/neck_controller',
        '/controller_manager','/move_group/moveit','/moveit_simple_controller_manager','/robotsystem',
        '/move_group_private_1','/moveit_2','/transform_listener_impl_abcdef')))
    scoped=tuple(namespace+name for name in base)
    assert RuntimeBinding.worker_node_inventory_matches(scoped,teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(base,teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(sorted(scoped+('/foreign/node',))),
        teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(n for n in scoped if not n.endswith('/neck_controller')),
        teacher_profile=True,namespace=namespace)


# ---- reset and evidence contexts (argument construction only) -----------------------------------------------------
# These tests build and inspect the arguments `rclpy.init` receives. They do not reach a ROS graph, so they do not prove that
# a real namespaced stack answers the reset and evidence calls; that needs a later real-container run.

NAMESPACE='/act/campaign/w00'
RESET_WORLD='/mujoco_ros2_control_node/reset_world'


class _InitReached(Exception):
    """Raised by the node factory so the call under test stops right after `rclpy.init`."""


@pytest.fixture
def init_calls(monkeypatch):
    import rclpy
    from so101_demo.backends.mujoco import teleop_runtime
    calls=[]
    def init(*args,**kwargs):
        calls.append((args,kwargs))
    def create_node(*args,**kwargs):
        raise _InitReached
    monkeypatch.setattr(rclpy,'init',init)
    monkeypatch.setattr(rclpy,'create_node',create_node)
    return teleop_runtime,calls


def reset_and_evidence_calls(teleop_runtime):
    for call in (lambda:teleop_runtime.current_evidence('session',timeout_s=.1),
                 lambda:teleop_runtime.transactional_reset('session',timeout_s=.1),
                 lambda:teleop_runtime.transactional_reset('session',timeout_s=.1,act_profile=True)):
        with pytest.raises(_InitReached):call()
        yield


def mark_container(monkeypatch):
    monkeypatch.setenv('SO101_ACT_CONTAINER_NAMESPACE',NAMESPACE)
    monkeypatch.setenv('ROS_NAMESPACE',NAMESPACE)


def test_reset_and_evidence_init_carry_container_remaps(init_calls,monkeypatch):
    teleop_runtime,calls=init_calls
    mark_container(monkeypatch)
    list(reset_and_evidence_calls(teleop_runtime))
    assert len(calls)==3
    for args,kwargs in calls:
        assert args==() and '__ns:='+NAMESPACE in kwargs['args']
        assert kwargs['args'][:2]==['--ros-args','-r']
        assert RESET_WORLD+':='+NAMESPACE+RESET_WORLD in kwargs['args']
        assert '/mujoco_ros2_control_node/set_pause:='+NAMESPACE+'/mujoco_ros2_control_node/set_pause' in kwargs['args']
        assert '/so101/simulation/evidence:='+NAMESPACE+'/so101/simulation/evidence' in kwargs['args']
        assert '/joint_states:='+NAMESPACE+'/joint_states' in kwargs['args']


def test_reset_world_is_remapped():
    import rclpy
    assert (RESET_WORLD,NAMESPACE+RESET_WORLD) in module().namespace_remappings(NAMESPACE)
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=NAMESPACE,ROS_NAMESPACE=NAMESPACE))
    context=rclpy.context.Context()
    context.init(**options,domain_id=232)
    node=None
    try:
        node=rclpy.create_node('reset_probe',context=context)
        assert node.resolve_service_name(RESET_WORLD)==NAMESPACE+RESET_WORLD
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


def test_marker_absent_keeps_bare_init(init_calls,monkeypatch):
    teleop_runtime,calls=init_calls
    monkeypatch.delenv('SO101_ACT_CONTAINER_NAMESPACE',raising=False)
    monkeypatch.setenv('ROS_NAMESPACE','/generic')
    list(reset_and_evidence_calls(teleop_runtime))
    assert calls==[((),{}),((),{}),((),{})]


def test_container_init_installs_no_signal_handlers(init_calls,monkeypatch):
    from rclpy.signals import SignalHandlerOptions
    teleop_runtime,calls=init_calls
    mark_container(monkeypatch)
    list(reset_and_evidence_calls(teleop_runtime))
    assert [kwargs['signal_handler_options'] for _args,kwargs in calls]==[SignalHandlerOptions.NO]*3
    # the shared options stay free of it: Context.init and the Recorder's own explicit option would otherwise collide
    assert 'signal_handler_options' not in module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=NAMESPACE,ROS_NAMESPACE=NAMESPACE))
    assert module().container_ros_global_init_options(environment={})=={}
